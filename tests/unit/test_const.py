#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.const のテスト"""

import pytest

from unit_cooler.const import AIRCON_MODE, COOLING_STATE, LOG_LEVEL, PUBSUB_CH, VALVE_STATE


class TestValveState:
    """VALVE_STATE のテスト"""

    def test_open_value(self):
        """OPEN は 1"""
        assert VALVE_STATE.OPEN == 1
        assert VALVE_STATE.OPEN.value == 1

    def test_close_value(self):
        """CLOSE は 0"""
        assert VALVE_STATE.CLOSE == 0
        assert VALVE_STATE.CLOSE.value == 0

    def test_from_int(self):
        """整数から変換できる"""
        assert VALVE_STATE(1) == VALVE_STATE.OPEN
        assert VALVE_STATE(0) == VALVE_STATE.CLOSE

    def test_invalid_value(self):
        """無効な値で例外"""
        with pytest.raises(ValueError):
            VALVE_STATE(2)

    def test_all_values(self):
        """全ての値が定義されている"""
        assert set(VALVE_STATE) == {VALVE_STATE.OPEN, VALVE_STATE.CLOSE}


class TestCoolingState:
    """COOLING_STATE のテスト"""

    def test_working_value(self):
        """WORKING は 1"""
        assert COOLING_STATE.WORKING == 1
        assert COOLING_STATE.WORKING.value == 1

    def test_idle_value(self):
        """IDLE は 0"""
        assert COOLING_STATE.IDLE == 0
        assert COOLING_STATE.IDLE.value == 0

    def test_from_int(self):
        """整数から変換できる"""
        assert COOLING_STATE(1) == COOLING_STATE.WORKING
        assert COOLING_STATE(0) == COOLING_STATE.IDLE

    def test_invalid_value(self):
        """無効な値で例外"""
        with pytest.raises(ValueError):
            COOLING_STATE(2)


class TestAirconMode:
    """AIRCON_MODE のテスト"""

    def test_off_value(self):
        """OFF は 0"""
        assert AIRCON_MODE.OFF == 0

    def test_idle_value(self):
        """IDLE は 1"""
        assert AIRCON_MODE.IDLE == 1

    def test_normal_value(self):
        """NORMAL は 2"""
        assert AIRCON_MODE.NORMAL == 2

    def test_full_value(self):
        """FULL は 3"""
        assert AIRCON_MODE.FULL == 3

    def test_all_values(self):
        """全ての値が定義されている"""
        expected = {AIRCON_MODE.OFF, AIRCON_MODE.IDLE, AIRCON_MODE.NORMAL, AIRCON_MODE.FULL}
        assert set(AIRCON_MODE) == expected

    def test_ordering(self):
        """値の順序が正しい"""
        assert AIRCON_MODE.OFF < AIRCON_MODE.IDLE < AIRCON_MODE.NORMAL < AIRCON_MODE.FULL


class TestLogLevel:
    """LOG_LEVEL のテスト"""

    def test_info_value(self):
        """INFO が定義されている"""
        assert LOG_LEVEL.INFO is not None

    def test_warn_value(self):
        """WARN が定義されている"""
        assert LOG_LEVEL.WARN is not None

    def test_error_value(self):
        """ERROR が定義されている"""
        assert LOG_LEVEL.ERROR is not None

    def test_ordering(self):
        """重大度の順序が正しい"""
        assert LOG_LEVEL.INFO < LOG_LEVEL.WARN < LOG_LEVEL.ERROR


class TestPubSubCh:
    """PUBSUB_CH のテスト"""

    def test_value(self):
        """チャンネル名が正しい"""
        assert PUBSUB_CH == "unit_cooler"

    def test_type(self):
        """文字列型"""
        assert isinstance(PUBSUB_CH, str)
