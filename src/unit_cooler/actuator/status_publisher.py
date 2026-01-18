#!/usr/bin/env python3
"""
ActuatorStatus を ZeroMQ で配信する機能を提供します。
"""

from __future__ import annotations

import json
import logging

import my_lib.time
import zmq

from unit_cooler.actuator.monitor import MistCondition
from unit_cooler.messages import ActuatorStatus, ControlMessage

logger = logging.getLogger(__name__)


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
    logger.info("ActuatorStatus publisher bound to %s:%d", host, port)
    return socket


def create_status(
    mist_condition: MistCondition,
    control_message: ControlMessage,
    hazard_detected: bool = False,
) -> ActuatorStatus:
    """ActuatorStatus を作成する

    Args:
        mist_condition: ミスト状態
        control_message: 制御メッセージ
        hazard_detected: ハザード検出フラグ

    Returns:
        ActuatorStatus インスタンス
    """
    return ActuatorStatus(
        timestamp=my_lib.time.now().isoformat(),
        valve=mist_condition.valve,
        flow_lpm=mist_condition.flow,
        cooling_mode_index=control_message.mode_index,
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
        logger.info("ActuatorStatus publisher closed")
    except Exception:
        logging.exception("Failed to close publisher")
