#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.monitor のテスト（漏水・詰まり・流量異常判定 = 安全機構の中核）"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import unit_cooler.actuator.monitor
from unit_cooler.const import LOG_LEVEL, VALVE_STATE
from unit_cooler.messages import ValveStatus


def _gen_handle(config) -> unit_cooler.actuator.monitor.MonitorHandle:
    """ネットワーク接続を伴う FluentSender を避けて MonitorHandle を直接生成する"""
    return unit_cooler.actuator.monitor.MonitorHandle(
        config=config,
        hostname="test-host",
        sender=MagicMock(),
        log_period=60,
    )


def _condition(state: VALVE_STATE, duration_sec: float, flow):
    return unit_cooler.actuator.monitor.MistCondition(
        valve=ValveStatus(state=state, duration_sec=duration_sec),
        flow=flow,
    )


class TestCheckSensing:
    """check_sensing のテスト（流量計の異常検知とリセット）"""

    def test_resets_unknown_when_flow_available(self, config):
        """流量が取得できたら flow_unknown を 0 に戻す"""
        handle = _gen_handle(config)
        handle.flow_unknown = 4

        unit_cooler.actuator.monitor.check_sensing(handle, _condition(VALVE_STATE.OPEN, 1.0, 1.5))

        assert handle.flow_unknown == 0

    def test_increments_unknown_without_action_between_intervals(self, config, mocker):
        """リセット周期に達しない間はログもリセットも行わない（スパム防止）"""
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mock_stop = mocker.patch("unit_cooler.actuator.sensor.stop")
        handle = _gen_handle(config)
        # giveup=5 → reset_interval=2。flow_unknown=2 → 3 は 3%2!=0 なので何もしない
        handle.flow_unknown = 2

        unit_cooler.actuator.monitor.check_sensing(handle, _condition(VALVE_STATE.OPEN, 1.0, None))

        assert handle.flow_unknown == 3
        mock_add.assert_not_called()
        mock_stop.assert_not_called()

    def test_warns_and_resets_below_giveup(self, config, mocker):
        """giveup 以下のリセット周期では WARN を出してセンサーをリセットする"""
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mock_stop = mocker.patch("unit_cooler.actuator.sensor.stop")
        handle = _gen_handle(config)
        handle.flow_unknown = 1  # → 2（reset_interval の倍数、giveup=5 以下）

        unit_cooler.actuator.monitor.check_sensing(handle, _condition(VALVE_STATE.OPEN, 1.0, None))

        assert handle.flow_unknown == 2
        mock_stop.assert_called_once()
        assert mock_add.call_args[0][1] == LOG_LEVEL.WARN

    def test_errors_and_keeps_resetting_above_giveup(self, config, mocker):
        """giveup 超過後も ERROR を出しつつリセットを継続する"""
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mock_stop = mocker.patch("unit_cooler.actuator.sensor.stop")
        handle = _gen_handle(config)
        handle.flow_unknown = 5  # → 6（giveup=5 超過、reset_interval=2 の倍数）

        unit_cooler.actuator.monitor.check_sensing(handle, _condition(VALVE_STATE.OPEN, 1.0, None))

        assert handle.flow_unknown == 6
        mock_stop.assert_called_once()
        assert mock_add.call_args[0][1] == LOG_LEVEL.ERROR


class TestCheckMistConditionOpen:
    """check_mist_condition のテスト（バルブ OPEN 時）"""

    def test_detects_water_leak(self, config, mocker):
        """OPEN 後一定時間経っても流量過大なら水漏れとしてハザード通知"""
        mock_hazard = mocker.patch("unit_cooler.actuator.control.hazard_notify")
        handle = _gen_handle(config)
        # on.max=[12,12,5,3.0]。flow=13 > 12 かつ duration=6 > 5*(0+1)
        unit_cooler.actuator.monitor.check_mist_condition(handle, _condition(VALVE_STATE.OPEN, 6.0, 13.0))

        mock_hazard.assert_called()

    def test_detects_closed_main_valve(self, config, mocker):
        """OPEN なのに流量が最低値未満なら元栓が閉じている可能性を記録（ハザードにはしない）"""
        mock_hazard = mocker.patch("unit_cooler.actuator.control.hazard_notify")
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        handle = _gen_handle(config)
        # on.min=0.02。flow=0.01 < 0.02 かつ duration=6 > 5
        unit_cooler.actuator.monitor.check_mist_condition(handle, _condition(VALVE_STATE.OPEN, 6.0, 0.01))

        mock_hazard.assert_not_called()
        assert mock_add.call_args[0][1] == LOG_LEVEL.ERROR

    def test_no_alert_for_normal_flow(self, config, mocker):
        """正常な流量ではハザードも元栓警告も出さない"""
        mock_hazard = mocker.patch("unit_cooler.actuator.control.hazard_notify")
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        handle = _gen_handle(config)
        # on.min=0.02 < flow=2.0 < on.max=12
        unit_cooler.actuator.monitor.check_mist_condition(handle, _condition(VALVE_STATE.OPEN, 6.0, 2.0))

        mock_hazard.assert_not_called()
        mock_add.assert_not_called()


class TestCheckMistConditionClose:
    """check_mist_condition のテスト（バルブ CLOSE 時）"""

    def test_detects_broken_valve(self, config, mocker):
        """CLOSE 後も流量が残っていれば電磁弁故障としてハザード通知"""
        mock_hazard = mocker.patch("unit_cooler.actuator.control.hazard_notify")
        handle = _gen_handle(config)
        # off.max=0.01。duration=121 > 120 かつ flow=0.5 > 0.01
        unit_cooler.actuator.monitor.check_mist_condition(handle, _condition(VALVE_STATE.CLOSE, 121.0, 0.5))

        mock_hazard.assert_called()

    def test_powers_off_sensor_after_long_close(self, config, mocker):
        """長時間 CLOSE かつ流量 0 なら流量計の電源を OFF する"""
        mocker.patch("unit_cooler.actuator.sensor.get_power_state", return_value=True)
        mock_add = mocker.patch("unit_cooler.actuator.work_log.add")
        mock_stop = mocker.patch("unit_cooler.actuator.sensor.stop")
        handle = _gen_handle(config)
        # power_off_sec=7200。duration=7201 >= 7200 かつ flow == 0
        unit_cooler.actuator.monitor.check_mist_condition(handle, _condition(VALVE_STATE.CLOSE, 7201.0, 0))

        mock_stop.assert_called_once()
        mock_add.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
