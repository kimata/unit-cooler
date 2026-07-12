#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.worker のテスト（ワーカーの例外耐性・フェイルセーフ・配信配線）"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import unit_cooler.actuator.control
import unit_cooler.actuator.monitor
import unit_cooler.actuator.worker
from unit_cooler.const import COOLING_STATE, VALVE_STATE
from unit_cooler.messages import ControlMessage, DutyConfig, ValveStatus


def _message(mode_index=3) -> ControlMessage:
    return ControlMessage(
        mode_index=mode_index,
        state=COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=60, off_sec=540),
    )


@pytest.fixture
def valve_controller_mock(mocker):
    """バルブコントローラのモック"""
    controller = MagicMock()
    mocker.patch("unit_cooler.actuator.valve_controller.get_valve_controller", return_value=controller)
    return controller


@pytest.fixture(autouse=True)
def _worker_state(mocker):
    """ワーカーのグローバル状態を初期化し、待機時間を無くす"""
    unit_cooler.actuator.worker.init_should_terminate()
    unit_cooler.actuator.worker.set_last_control_message(unit_cooler.actuator.worker.MESSAGE_INIT)
    mocker.patch("unit_cooler.actuator.worker.sleep_until_next_iter")
    mocker.patch("my_lib.footprint.update")


class TestControlWorker:
    """control_worker のテスト"""

    def test_terminates_by_msg_count(self, config, mocker, tmp_path, valve_controller_mock):
        """msg_count 到達で正常終了する"""
        handle = MagicMock()
        handle.receive_count = 0
        mocker.patch("unit_cooler.actuator.control.gen_handle", return_value=handle)

        def fake_get_control_message(handle_, last_message):
            handle.receive_count = 1
            return _message()

        mock_get = mocker.patch(
            "unit_cooler.actuator.control.get_control_message", side_effect=fake_get_control_message
        )
        mocker.patch("unit_cooler.actuator.control.execute", return_value=_message())

        ret = unit_cooler.actuator.worker.control_worker(
            config, MagicMock(), tmp_path / "liveness", msg_count=1
        )

        assert ret == 0
        assert mock_get.call_count == 1

    def test_survives_transient_exception(self, config, mocker, tmp_path, valve_controller_mock):
        """一過性の例外 1 回では停止せず、通知して継続する (P1-2)"""
        handle = MagicMock()
        handle.receive_count = 0
        mocker.patch("unit_cooler.actuator.control.gen_handle", return_value=handle)

        calls = {"count": 0}

        def fake_get_control_message(handle_, last_message):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient error")
            handle.receive_count = 1
            return _message()

        mocker.patch("unit_cooler.actuator.control.get_control_message", side_effect=fake_get_control_message)
        mock_execute = mocker.patch("unit_cooler.actuator.control.execute", return_value=_message())
        mock_notify = mocker.patch("unit_cooler.util.notify_error")

        ret = unit_cooler.actuator.worker.control_worker(
            config, MagicMock(), tmp_path / "liveness", msg_count=1
        )

        # 例外の次のイテレーションで処理が継続し、正常終了する
        assert ret == 0
        assert calls["count"] == 2
        assert mock_execute.call_count == 1
        mock_notify.assert_called_once()

    def test_closes_valve_on_normal_exit(self, config, mocker, tmp_path, valve_controller_mock):
        """終了時（return 経路）にバルブを閉じる"""
        handle = MagicMock()
        handle.receive_count = 1
        mocker.patch("unit_cooler.actuator.control.gen_handle", return_value=handle)
        mocker.patch("unit_cooler.actuator.control.get_control_message", return_value=_message())
        mocker.patch("unit_cooler.actuator.control.execute", return_value=_message())

        unit_cooler.actuator.worker.control_worker(config, MagicMock(), tmp_path / "liveness", msg_count=1)

        valve_controller_mock.close.assert_called_once()

    def test_closes_valve_on_fatal_exception(self, config, mocker, tmp_path, valve_controller_mock):
        """致命的エラーで脱出する場合も -1 を返しつつバルブを閉じる"""
        handle = MagicMock()
        handle.receive_count = 0
        mocker.patch("unit_cooler.actuator.control.gen_handle", return_value=handle)
        mocker.patch("unit_cooler.actuator.control.get_control_message", return_value=_message())
        mocker.patch("unit_cooler.actuator.control.execute", return_value=_message())
        mocker.patch("unit_cooler.util.notify_error")
        # イテレーション単位の try の外側で例外を発生させる
        mocker.patch("unit_cooler.actuator.worker.sleep_until_next_iter", side_effect=RuntimeError("fatal"))

        ret = unit_cooler.actuator.worker.control_worker(
            config, MagicMock(), tmp_path / "liveness", msg_count=0
        )

        assert ret == -1
        valve_controller_mock.close.assert_called_once()

    def test_uninitialized_valve_controller_is_tolerated(self, config, mocker, tmp_path):
        """バルブ未初期化（RuntimeError）でも finally の閉弁処理で落ちない"""
        handle = MagicMock()
        handle.receive_count = 1
        mocker.patch("unit_cooler.actuator.control.gen_handle", return_value=handle)
        mocker.patch("unit_cooler.actuator.control.get_control_message", return_value=_message())
        mocker.patch("unit_cooler.actuator.control.execute", return_value=_message())
        mocker.patch(
            "unit_cooler.actuator.valve_controller.get_valve_controller",
            side_effect=RuntimeError("not initialized"),
        )

        ret = unit_cooler.actuator.worker.control_worker(
            config, MagicMock(), tmp_path / "liveness", msg_count=1
        )

        assert ret == 0

    def test_stores_effective_message(self, config, mocker, tmp_path, valve_controller_mock):
        """execute の戻り値（実効メッセージ）を last_control_message として保存する (P2-11)"""
        handle = MagicMock()
        handle.receive_count = 1
        mocker.patch("unit_cooler.actuator.control.gen_handle", return_value=handle)
        raw_message = _message(mode_index=3)
        effective_message = unit_cooler.actuator.control.MESSAGE_IDLE
        mocker.patch("unit_cooler.actuator.control.get_control_message", return_value=raw_message)
        mocker.patch("unit_cooler.actuator.control.execute", return_value=effective_message)

        unit_cooler.actuator.worker.control_worker(config, MagicMock(), tmp_path / "liveness", msg_count=1)

        # ハザード等で IDLE に差し替えられたメッセージが monitor 側から見えること
        assert unit_cooler.actuator.worker.get_last_control_message() == effective_message


class TestMonitorWorker:
    """monitor_worker のテスト"""

    @pytest.fixture
    def monitor_mocks(self, mocker):
        """monitor_worker のループ 1 回分を回すためのモック一式"""
        handle = MagicMock()
        handle.log_period = 1
        # NOTE: msg_count=1 のとき monitor_count >= 21 で終了するので、1 周で終わる値にする
        handle.monitor_count = 100
        mocker.patch("unit_cooler.actuator.monitor.gen_handle", return_value=handle)
        mocker.patch(
            "unit_cooler.actuator.monitor.get_mist_condition",
            return_value=unit_cooler.actuator.monitor.MistCondition(
                valve=ValveStatus(state=VALVE_STATE.CLOSE, duration_sec=1.0), flow=0.0
            ),
        )
        mocker.patch("unit_cooler.actuator.monitor.check")
        mocker.patch("unit_cooler.actuator.monitor.send_mist_condition")
        mocker.patch("unit_cooler.actuator.status_publisher.create_publisher", return_value=MagicMock())
        mocker.patch("unit_cooler.actuator.status_publisher.publish_status")
        mocker.patch("unit_cooler.actuator.status_publisher.close_publisher")
        return mocker.patch("unit_cooler.actuator.status_publisher.create_status", return_value=MagicMock())

    @pytest.mark.parametrize("hazard_exists", [True, False])
    def test_passes_hazard_detected_to_status(self, config, mocker, tmp_path, monitor_mocks, hazard_exists):
        """ハザードラッチの有無が ActuatorStatus の hazard_detected に配線される (P2-1)"""
        mocker.patch("my_lib.footprint.exists", return_value=hazard_exists)

        ret = unit_cooler.actuator.worker.monitor_worker(
            config, tmp_path / "liveness", msg_count=1, status_pub_port=5555
        )

        assert ret == 0
        monitor_mocks.assert_called_once()
        assert monitor_mocks.call_args.kwargs["hazard_detected"] is hazard_exists


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
