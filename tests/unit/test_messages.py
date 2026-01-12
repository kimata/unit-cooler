#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.messages のテスト"""

import json

import pytest

from unit_cooler.const import COOLING_STATE, VALVE_STATE
from unit_cooler.messages import ActuatorStatus, ControlMessage, DutyConfig, ValveStatus


class TestDutyConfig:
    """DutyConfig のテスト"""

    def test_create(self):
        """基本的な作成"""
        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        assert duty.enable is True
        assert duty.on_sec == 60
        assert duty.off_sec == 30

    def test_frozen(self):
        """frozen dataclass"""
        import dataclasses

        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        with pytest.raises(dataclasses.FrozenInstanceError):
            duty.enable = False  # type: ignore

    def test_to_dict(self):
        """dict 変換"""
        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        d = duty.to_dict()
        assert d == {"enable": True, "on_sec": 60, "off_sec": 30}

    def test_from_dict(self):
        """dict からの作成"""
        data = {"enable": False, "on_sec": 120, "off_sec": 60}
        duty = DutyConfig.from_dict(data)
        assert duty.enable is False
        assert duty.on_sec == 120
        assert duty.off_sec == 60

    def test_roundtrip(self):
        """to_dict と from_dict のラウンドトリップ"""
        original = DutyConfig(enable=True, on_sec=100, off_sec=50)
        restored = DutyConfig.from_dict(original.to_dict())
        assert restored == original


class TestControlMessage:
    """ControlMessage のテスト"""

    def test_create(self):
        """基本的な作成"""
        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        msg = ControlMessage(
            state=COOLING_STATE.WORKING,
            duty=duty,
            mode_index=2,
        )
        assert msg.state == COOLING_STATE.WORKING
        assert msg.duty == duty
        assert msg.mode_index == 2
        assert msg.sense_data == {}

    def test_with_sense_data(self):
        """sense_data 付きの作成"""
        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        sense_data = {"temp": 30.5, "humi": 60}
        msg = ControlMessage(
            state=COOLING_STATE.IDLE,
            duty=duty,
            mode_index=0,
            sense_data=sense_data,
        )
        assert msg.sense_data == sense_data

    def test_to_dict(self):
        """dict 変換"""
        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        msg = ControlMessage(
            state=COOLING_STATE.WORKING,
            duty=duty,
            mode_index=3,
            sense_data={"temp": 25},
        )
        d = msg.to_dict()
        assert d["state"] == COOLING_STATE.WORKING.value
        assert d["duty"] == {"enable": True, "on_sec": 60, "off_sec": 30}
        assert d["mode_index"] == 3
        assert d["sense_data"] == {"temp": 25}

    def test_to_json(self):
        """JSON 変換"""
        duty = DutyConfig(enable=True, on_sec=60, off_sec=30)
        msg = ControlMessage(
            state=COOLING_STATE.WORKING,
            duty=duty,
            mode_index=1,
        )
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["state"] == 1
        assert data["mode_index"] == 1

    def test_from_dict(self):
        """dict からの作成"""
        data = {
            "state": 1,
            "duty": {"enable": False, "on_sec": 90, "off_sec": 45},
            "mode_index": 2,
            "sense_data": {"power": 500},
        }
        msg = ControlMessage.from_dict(data)
        assert msg.state == COOLING_STATE.WORKING
        assert msg.duty.enable is False
        assert msg.mode_index == 2
        assert msg.sense_data == {"power": 500}

    def test_from_dict_without_sense_data(self):
        """sense_data なしの dict からの作成"""
        data = {
            "state": 0,
            "duty": {"enable": True, "on_sec": 60, "off_sec": 30},
            "mode_index": 0,
        }
        msg = ControlMessage.from_dict(data)
        assert msg.sense_data == {}

    def test_from_json(self):
        """JSON からの作成"""
        json_str = '{"state": 1, "duty": {"enable": true, "on_sec": 60, "off_sec": 30}, "mode_index": 1}'
        msg = ControlMessage.from_json(json_str)
        assert msg.state == COOLING_STATE.WORKING
        assert msg.duty.enable is True

    def test_roundtrip(self):
        """to_json と from_json のラウンドトリップ"""
        duty = DutyConfig(enable=True, on_sec=120, off_sec=60)
        original = ControlMessage(
            state=COOLING_STATE.WORKING,
            duty=duty,
            mode_index=5,
            sense_data={"temp": 35, "power": 800},
        )
        restored = ControlMessage.from_json(original.to_json())
        assert restored.state == original.state
        assert restored.duty == original.duty
        assert restored.mode_index == original.mode_index
        assert restored.sense_data == original.sense_data


class TestValveStatus:
    """ValveStatus のテスト"""

    def test_create(self):
        """基本的な作成"""
        status = ValveStatus(state=VALVE_STATE.OPEN, duration_sec=120.5)
        assert status.state == VALVE_STATE.OPEN
        assert status.duration_sec == 120.5

    def test_to_dict(self):
        """dict 変換"""
        status = ValveStatus(state=VALVE_STATE.CLOSE, duration_sec=30.0)
        d = status.to_dict()
        assert d == {"state": 0, "duration": 30.0}

    def test_from_dict(self):
        """dict からの作成"""
        data = {"state": 1, "duration": 60.5}
        status = ValveStatus.from_dict(data)
        assert status.state == VALVE_STATE.OPEN
        assert status.duration_sec == 60.5

    def test_roundtrip(self):
        """to_dict と from_dict のラウンドトリップ"""
        original = ValveStatus(state=VALVE_STATE.OPEN, duration_sec=45.5)
        restored = ValveStatus.from_dict(original.to_dict())
        assert restored == original


class TestActuatorStatus:
    """ActuatorStatus のテスト"""

    def test_create(self):
        """基本的な作成"""
        valve = ValveStatus(state=VALVE_STATE.OPEN, duration_sec=30.0)
        status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve,
            flow_lpm=2.5,
            cooling_mode_index=3,
            hazard_detected=False,
        )
        assert status.timestamp == "2024-01-01T12:00:00"
        assert status.valve == valve
        assert status.flow_lpm == 2.5
        assert status.cooling_mode_index == 3
        assert status.hazard_detected is False

    def test_with_none_flow(self):
        """flow_lpm が None の場合"""
        valve = ValveStatus(state=VALVE_STATE.CLOSE, duration_sec=0.0)
        status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve,
            flow_lpm=None,
            cooling_mode_index=0,
            hazard_detected=True,
        )
        assert status.flow_lpm is None

    def test_to_dict(self):
        """dict 変換"""
        valve = ValveStatus(state=VALVE_STATE.OPEN, duration_sec=60.0)
        status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve,
            flow_lpm=3.0,
            cooling_mode_index=2,
            hazard_detected=False,
        )
        d = status.to_dict()
        assert d["timestamp"] == "2024-01-01T12:00:00"
        assert d["valve"] == {"state": 1, "duration": 60.0}
        assert d["flow_lpm"] == 3.0
        assert d["cooling_mode_index"] == 2
        assert d["hazard_detected"] is False

    def test_to_json(self):
        """JSON 変換"""
        valve = ValveStatus(state=VALVE_STATE.CLOSE, duration_sec=0.0)
        status = ActuatorStatus(
            timestamp="2024-01-01T12:00:00",
            valve=valve,
            flow_lpm=None,
            cooling_mode_index=0,
            hazard_detected=False,
        )
        json_str = status.to_json()
        data = json.loads(json_str)
        assert data["flow_lpm"] is None

    def test_from_dict(self):
        """dict からの作成"""
        data = {
            "timestamp": "2024-06-15T15:30:00",
            "valve": {"state": 1, "duration": 120.0},
            "flow_lpm": 4.5,
            "cooling_mode_index": 4,
            "hazard_detected": True,
        }
        status = ActuatorStatus.from_dict(data)
        assert status.timestamp == "2024-06-15T15:30:00"
        assert status.valve.state == VALVE_STATE.OPEN
        assert status.valve.duration_sec == 120.0
        assert status.flow_lpm == 4.5
        assert status.cooling_mode_index == 4
        assert status.hazard_detected is True

    def test_from_json(self):
        """JSON からの作成"""
        json_str = """
        {
            "timestamp": "2024-01-01T00:00:00",
            "valve": {"state": 0, "duration": 0},
            "flow_lpm": null,
            "cooling_mode_index": 0,
            "hazard_detected": false
        }
        """
        status = ActuatorStatus.from_json(json_str)
        assert status.valve.state == VALVE_STATE.CLOSE
        assert status.flow_lpm is None

    def test_roundtrip(self):
        """to_json と from_json のラウンドトリップ"""
        valve = ValveStatus(state=VALVE_STATE.OPEN, duration_sec=300.0)
        original = ActuatorStatus(
            timestamp="2024-12-25T10:00:00",
            valve=valve,
            flow_lpm=5.5,
            cooling_mode_index=6,
            hazard_detected=False,
        )
        restored = ActuatorStatus.from_json(original.to_json())
        assert restored.timestamp == original.timestamp
        assert restored.valve.state == original.valve.state
        assert restored.valve.duration_sec == original.valve.duration_sec
        assert restored.flow_lpm == original.flow_lpm
        assert restored.cooling_mode_index == original.cooling_mode_index
        assert restored.hazard_detected == original.hazard_detected
