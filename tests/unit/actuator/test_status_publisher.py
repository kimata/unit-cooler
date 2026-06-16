#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.status_publisher のテスト"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import unit_cooler.actuator.status_publisher
from unit_cooler.actuator.monitor import MistCondition
from unit_cooler.const import COOLING_STATE, VALVE_STATE
from unit_cooler.messages import ControlMessage, DutyConfig, ValveStatus


def _mist_condition(flow=1.5) -> MistCondition:
    return MistCondition(valve=ValveStatus(state=VALVE_STATE.OPEN, duration_sec=10.0), flow=flow)


def _control_message(mode_index=3) -> ControlMessage:
    return ControlMessage(
        mode_index=mode_index,
        state=COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=10, off_sec=5),
    )


class TestCreateStatus:
    """create_status のテスト"""

    def test_maps_fields_from_condition_and_message(self):
        """MistCondition と ControlMessage から ActuatorStatus を構築する"""
        status = unit_cooler.actuator.status_publisher.create_status(
            _mist_condition(flow=2.5), _control_message(mode_index=4), hazard_detected=True
        )

        assert status.valve.state == VALVE_STATE.OPEN
        assert status.flow_lpm == 2.5
        assert status.cooling_mode_index == 4
        assert status.hazard_detected is True
        assert isinstance(status.timestamp, str)

    def test_hazard_defaults_to_false(self):
        """hazard_detected の既定値は False"""
        status = unit_cooler.actuator.status_publisher.create_status(_mist_condition(), _control_message())

        assert status.hazard_detected is False

    def test_flow_none_is_preserved(self):
        """流量が None の場合もそのまま保持する"""
        status = unit_cooler.actuator.status_publisher.create_status(
            _mist_condition(flow=None), _control_message()
        )

        assert status.flow_lpm is None


class TestPublishStatus:
    """publish_status のテスト"""

    def test_sends_topic_and_json(self):
        """トピック付きで JSON を送信し True を返す"""
        socket = MagicMock()
        status = unit_cooler.actuator.status_publisher.create_status(_mist_condition(), _control_message())

        result = unit_cooler.actuator.status_publisher.publish_status(socket, status)

        assert result is True
        socket.send_string.assert_called_once()
        sent = socket.send_string.call_args[0][0]
        topic, payload = sent.split(" ", 1)
        assert topic == "actuator_status"
        # ペイロードが ActuatorStatus.to_dict() の JSON であること
        assert json.loads(payload) == status.to_dict()

    def test_returns_false_on_error(self):
        """送信失敗時は False を返す"""
        socket = MagicMock()
        socket.send_string.side_effect = RuntimeError("boom")
        status = unit_cooler.actuator.status_publisher.create_status(_mist_condition(), _control_message())

        result = unit_cooler.actuator.status_publisher.publish_status(socket, status)

        assert result is False


class TestPublisherLifecycle:
    """create_publisher / close_publisher のテスト"""

    def test_create_publisher_binds(self, mocker):
        """PUB ソケットを生成して指定ポートにバインドする"""
        mock_socket = MagicMock()
        mock_context = MagicMock()
        mock_context.socket.return_value = mock_socket
        mocker.patch("zmq.Context", return_value=mock_context)

        socket = unit_cooler.actuator.status_publisher.create_publisher("127.0.0.1", 5800)

        assert socket is mock_socket
        mock_socket.bind.assert_called_once_with("tcp://127.0.0.1:5800")

    def test_close_publisher_swallows_errors(self):
        """close 時の例外は送出しない"""
        socket = MagicMock()
        socket.close.side_effect = RuntimeError("boom")

        # 例外を送出しないこと
        unit_cooler.actuator.status_publisher.close_publisher(socket)

        socket.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
