#!/usr/bin/env python3
"""
ActuatorStatus を ZeroMQ で配信する機能を提供します。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import my_lib.time
import zmq

from unit_cooler.actuator.monitor import MistCondition
from unit_cooler.messages import ActuatorStatus, ControlMessage

logger = logging.getLogger(__name__)


@dataclass
class StatusPublisherHandle:
    """ActuatorStatus 配信用の ZeroMQ ハンドル"""

    context: zmq.Context
    socket: zmq.Socket


def create_publisher(host: str, port: int) -> StatusPublisherHandle:
    """ZeroMQ Publisher を作成する

    Args:
        host: バインドするホスト
        port: バインドするポート

    Returns:
        StatusPublisherHandle
    """
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://{host}:{port}")
    logger.info("ActuatorStatus publisher bound to %s:%d", host, port)
    return StatusPublisherHandle(context=context, socket=socket)


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


def publish_status(handle: StatusPublisherHandle, status: ActuatorStatus) -> bool:
    """ActuatorStatus を配信する

    Args:
        handle: StatusPublisherHandle
        status: ActuatorStatus

    Returns:
        送信成功したかどうか
    """
    try:
        # トピック付きでメッセージを送信
        topic = "actuator_status"
        message = json.dumps(status.to_dict())
        handle.socket.send_string(f"{topic} {message}")
        logger.debug("Published ActuatorStatus: %s", message)
        return True
    except Exception:
        logger.exception("Failed to publish ActuatorStatus")
        return False


def close_publisher(handle: StatusPublisherHandle) -> None:
    """Publisher を閉じる（ソケットとコンテキストの両方を解放する）

    Args:
        handle: StatusPublisherHandle
    """
    try:
        handle.socket.close()
        handle.context.term()
        logger.info("ActuatorStatus publisher closed")
    except Exception:
        logger.exception("Failed to close publisher")
