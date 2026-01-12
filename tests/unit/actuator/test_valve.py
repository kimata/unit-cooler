#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.valve のテスト"""

from __future__ import annotations

import pytest

import unit_cooler.actuator.valve
from unit_cooler.const import COOLING_STATE, VALVE_STATE


class TestValveInit:
    """valve.init のテスト"""

    def test_init_creates_controller(self, config, mocker):
        """init で ValveController を作成"""
        mocker.patch("my_lib.rpi.gpio")
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")

        unit_cooler.actuator.valve.init(17, config)

        assert unit_cooler.actuator.valve._controller is not None


class TestValveNotInitialized:
    """初期化前のエラーテスト"""

    def setup_method(self):
        """各テスト前に _controller をリセット"""
        unit_cooler.actuator.valve._controller = None

    def test_set_state_raises_without_init(self):
        """init なしで set_state は例外"""
        with pytest.raises(RuntimeError, match="not initialized"):
            unit_cooler.actuator.valve.set_state(VALVE_STATE.OPEN)

    def test_get_state_raises_without_init(self):
        """init なしで get_state は例外"""
        with pytest.raises(RuntimeError, match="not initialized"):
            unit_cooler.actuator.valve.get_state()

    def test_get_status_raises_without_init(self):
        """init なしで get_status は例外"""
        with pytest.raises(RuntimeError, match="not initialized"):
            unit_cooler.actuator.valve.get_status()

    def test_set_cooling_working_raises_without_init(self):
        """init なしで set_cooling_working は例外"""
        with pytest.raises(RuntimeError, match="not initialized"):
            unit_cooler.actuator.valve.set_cooling_working({"enable": True, "on_sec": 100, "off_sec": 60})

    def test_set_cooling_idle_raises_without_init(self):
        """init なしで set_cooling_idle は例外"""
        with pytest.raises(RuntimeError, match="not initialized"):
            unit_cooler.actuator.valve.set_cooling_idle()

    def test_set_cooling_state_raises_without_init(self):
        """init なしで set_cooling_state は例外"""
        with pytest.raises(RuntimeError, match="not initialized"):
            unit_cooler.actuator.valve.set_cooling_state({"state": COOLING_STATE.IDLE})


class TestValveSetState:
    """valve.set_state のテスト"""

    def test_set_state_returns_dict(self, config, mocker):
        """set_state が dict を返す"""
        mocker.patch("my_lib.rpi.gpio")
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("my_lib.footprint.exists", return_value=True)
        mocker.patch("my_lib.footprint.elapsed", return_value=10)

        unit_cooler.actuator.valve.init(17, config)
        result = unit_cooler.actuator.valve.set_state(VALVE_STATE.CLOSE)

        assert isinstance(result, dict)
        assert "state" in result
        assert "duration" in result


class TestValveGetState:
    """valve.get_state のテスト"""

    def test_get_state_returns_valve_state(self, config, mocker):
        """get_state が VALVE_STATE を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")

        unit_cooler.actuator.valve.init(17, config)
        state = unit_cooler.actuator.valve.get_state()

        assert state == VALVE_STATE.CLOSE


class TestValveGetStatus:
    """valve.get_status のテスト"""

    def test_get_status_returns_dict(self, config, mocker):
        """get_status が dict を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("my_lib.footprint.exists", return_value=True)
        mocker.patch("my_lib.footprint.elapsed", return_value=20)

        unit_cooler.actuator.valve.init(17, config)
        status = unit_cooler.actuator.valve.get_status()

        assert isinstance(status, dict)
        assert "state" in status
        assert "duration" in status
        assert status["state"] == VALVE_STATE.CLOSE
        assert status["duration"] == 20


class TestValveSetCoolingWorking:
    """valve.set_cooling_working のテスト"""

    def test_set_cooling_working_returns_dict(self, config, mocker):
        """set_cooling_working が dict を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mocker.patch("unit_cooler.actuator.work_log.add")

        unit_cooler.actuator.valve.init(17, config)
        result = unit_cooler.actuator.valve.set_cooling_working(
            {"enable": True, "on_sec": 100, "off_sec": 60}
        )

        assert isinstance(result, dict)
        assert "state" in result
        assert "duration" in result


class TestValveSetCoolingIdle:
    """valve.set_cooling_idle のテスト"""

    def test_set_cooling_idle_returns_dict(self, config, mocker):
        """set_cooling_idle が dict を返す"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mocker.patch("unit_cooler.actuator.work_log.add")

        unit_cooler.actuator.valve.init(17, config)
        result = unit_cooler.actuator.valve.set_cooling_idle()

        assert isinstance(result, dict)
        assert "state" in result
        assert "duration" in result


class TestValveSetCoolingState:
    """valve.set_cooling_state のテスト"""

    def test_set_cooling_state_working(self, config, mocker):
        """WORKING 状態で set_cooling_state"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        # 初期化時は CLOSE、set_cooling_state 時は CLOSE -> OPEN
        mock_gpio.input.side_effect = [0, 0, 0, 1, 1, 1, 1]

        # footprint の状態をトラッキング
        footprint_state = {
            "valve/open": False,
            "valve/close": False,
            "state/working": False,
            "state/idle": True,
        }

        def exists_side_effect(path):
            path_str = str(path)
            for key in footprint_state:
                if key in path_str:
                    return footprint_state[key]
            return True

        def update_side_effect(path):
            path_str = str(path)
            for key in footprint_state:
                if key in path_str:
                    footprint_state[key] = True

        def clear_side_effect(path):
            path_str = str(path)
            for key in footprint_state:
                if key in path_str:
                    footprint_state[key] = False

        mocker.patch("my_lib.footprint.clear", side_effect=clear_side_effect)
        mocker.patch("my_lib.footprint.update", side_effect=update_side_effect)
        mocker.patch("my_lib.footprint.exists", side_effect=exists_side_effect)
        mocker.patch("my_lib.footprint.elapsed", return_value=10.0)
        mocker.patch("unit_cooler.actuator.work_log.add")

        unit_cooler.actuator.valve.init(17, config)
        result = unit_cooler.actuator.valve.set_cooling_state(
            {
                "state": COOLING_STATE.WORKING,
                "duty": {"enable": True, "on_sec": 100, "off_sec": 60},
            }
        )

        assert isinstance(result, dict)
        assert result["state"] == VALVE_STATE.OPEN

    def test_set_cooling_state_idle(self, config, mocker):
        """IDLE 状態で set_cooling_state"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")
        mocker.patch("my_lib.footprint.exists", return_value=False)
        mocker.patch("unit_cooler.actuator.work_log.add")

        unit_cooler.actuator.valve.init(17, config)
        result = unit_cooler.actuator.valve.set_cooling_state(
            {
                "state": COOLING_STATE.IDLE,
            }
        )

        assert isinstance(result, dict)
        assert result["state"] == VALVE_STATE.CLOSE


class TestValveClearStat:
    """valve.clear_stat のテスト"""

    def test_clear_stat_without_init(self):
        """init なしでも clear_stat は例外なし"""
        unit_cooler.actuator.valve._controller = None
        unit_cooler.actuator.valve.clear_stat()  # 例外なし

    def test_clear_stat_with_init(self, config, mocker):
        """init 後に clear_stat"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")

        unit_cooler.actuator.valve.init(17, config)
        unit_cooler.actuator.valve.clear_stat()  # 例外なし


class TestValveGetHist:
    """valve.get_hist のテスト"""

    def test_get_hist_without_init(self):
        """init なしで空リスト"""
        unit_cooler.actuator.valve._controller = None
        hist = unit_cooler.actuator.valve.get_hist()

        assert hist == []

    def test_get_hist_with_init(self, config, mocker):
        """init 後に get_hist"""
        mock_gpio = mocker.patch("my_lib.rpi.gpio")
        mock_gpio.input.return_value = 0
        mocker.patch("my_lib.footprint.clear")
        mocker.patch("my_lib.footprint.update")

        unit_cooler.actuator.valve.init(17, config)
        hist = unit_cooler.actuator.valve.get_hist()

        assert isinstance(hist, list)
