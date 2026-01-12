#!/usr/bin/env python3
"""
ActuatorStatus を ZeroMQ で配信する機能を提供します。
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

import zmq

from unit_cooler.messages import ActuatorStatus, ValveStatus


def create_publisher(host: str, port: int) -> zmq.Socket:
    """ZeroMQ Publisher ソケットを作成する

    Args:
        host: バインドするホスト
        port: バインドするポート

    Returns:
        ZeroMQ Socket
    """
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://{host}:{port}")
    logging.info("ActuatorStatus publisher bound to %s:%d", host, port)
    return socket


def create_status(
    mist_condition: dict[str, Any],
    control_message: dict[str, Any] | None,
    hazard_detected: bool = False,
) -> ActuatorStatus:
    """ActuatorStatus を作成する

    Args:
        mist_condition: ミスト状態 (valve, flow を含む dict)
        control_message: 制御メッセージ (mode_index を含む dict)
        hazard_detected: ハザード検出フラグ

    Returns:
        ActuatorStatus インスタンス
    """
    valve_data = mist_condition["valve"]

    # ValveStatus を作成
    valve_status = ValveStatus(
        state=valve_data["state"],
        duration_sec=valve_data["duration"],
    )

    return ActuatorStatus(
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        valve=valve_status,
        flow_lpm=mist_condition["flow"],
        cooling_mode_index=control_message["mode_index"] if control_message else 0,
        hazard_detected=hazard_detected,
    )


def publish_status(socket: zmq.Socket, status: ActuatorStatus) -> bool:
    """ActuatorStatus を配信する

    Args:
        socket: ZeroMQ Socket
        status: ActuatorStatus

    Returns:
        送信成功したかどうか
    """
    try:
        # トピック付きでメッセージを送信
        topic = "actuator_status"
        message = json.dumps(status.to_dict())
        socket.send_string(f"{topic} {message}")
        logging.debug("Published ActuatorStatus: %s", message)
        return True
    except Exception:
        logging.exception("Failed to publish ActuatorStatus")
        return False


def close_publisher(socket: zmq.Socket) -> None:
    """Publisher ソケットを閉じる

    Args:
        socket: ZeroMQ Socket
    """
    try:
        socket.close()
        logging.info("ActuatorStatus publisher closed")
    except Exception:
        logging.exception("Failed to close publisher")
