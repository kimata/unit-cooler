#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import pathlib
import threading
import traceback
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import zmq

import unit_cooler.const
import unit_cooler.pubsub.subscribe
import unit_cooler.util
from unit_cooler.messages import ActuatorStatus

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

# グローバル終了フラグ
should_terminate = threading.Event()

# 最新の ActuatorStatus を保持
_last_actuator_status: ActuatorStatus | None = None
_actuator_status_lock = threading.Lock()


def get_last_actuator_status() -> ActuatorStatus | None:
    """最新の ActuatorStatus を取得する"""
    with _actuator_status_lock:
        return _last_actuator_status


def set_last_actuator_status(status: ActuatorStatus) -> None:
    """ActuatorStatus を設定する"""
    global _last_actuator_status
    with _actuator_status_lock:
        _last_actuator_status = status


def term() -> None:
    """終了フラグを設定する関数"""
    should_terminate.set()
    logging.info("Termination flag set for webui worker")


def queue_put(message_queue: Queue[Any], message: dict[str, Any], liveness_file: pathlib.Path) -> None:
    message["state"] = unit_cooler.const.COOLING_STATE(message["state"])

    if message_queue.full():
        message_queue.get()

    logging.info("Receive message: %s", message)

    message_queue.put(message)
    my_lib.footprint.update(liveness_file)


# NOTE: 制御メッセージを Subscribe して、キューに積み、cooler_stat.py で WebUI に渡すワーカ
def subscribe_worker(
    config: Config,
    control_host: str,
    pub_port: int,
    message_queue: Queue[Any],
    liveness_file: pathlib.Path,
    msg_count: int = 0,
) -> int:
    logging.info("Start webui subscribe worker (%s:%d)", control_host, pub_port)

    ret = 0
    try:
        # 終了フラグを渡してstart_clientを呼び出し
        unit_cooler.pubsub.subscribe.start_client(
            control_host,
            pub_port,
            lambda message: queue_put(message_queue, message, liveness_file),
            msg_count,
            should_terminate,
        )
    except Exception:
        logging.exception("Failed to receive control message")
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1

    logging.warning("Stop subscribe worker")

    return ret


# NOTE: ActuatorStatus を Subscribe して、キャッシュするワーカ
def actuator_status_worker(
    config: Config,
    actuator_host: str,
    status_pub_port: int,
) -> int:
    """ActuatorStatus を購読するワーカ

    Args:
        config: 設定
        actuator_host: Actuator のホスト名
        status_pub_port: ActuatorStatus 配信ポート

    Returns:
        終了コード (0: 正常, -1: エラー)
    """
    if status_pub_port <= 0:
        logging.info("ActuatorStatus subscription disabled (port=%d)", status_pub_port)
        return 0

    logging.info("Start actuator status worker (%s:%d)", actuator_host, status_pub_port)

    ret = 0
    context = None
    socket = None
    try:
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(f"tcp://{actuator_host}:{status_pub_port}")
        socket.setsockopt_string(zmq.SUBSCRIBE, "actuator_status")
        socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒タイムアウト

        logging.info("Connected to ActuatorStatus publisher")

        while not should_terminate.is_set():
            try:
                message = socket.recv_string()
                # メッセージ形式: "actuator_status {json_data}"
                if message.startswith("actuator_status "):
                    json_data = message[len("actuator_status ") :]
                    data = json.loads(json_data)
                    status = ActuatorStatus.from_dict(data)
                    set_last_actuator_status(status)
                    logging.debug("Received ActuatorStatus: %s", status)
            except zmq.Again:
                # タイムアウト - 終了フラグをチェックして継続
                continue
            except Exception:
                logging.debug("Failed to parse ActuatorStatus")

    except Exception:
        logging.exception("Failed to subscribe ActuatorStatus")
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1
    finally:
        if socket is not None:
            socket.close()
        if context is not None:
            context.term()

    logging.warning("Stop actuator status worker")
    return ret
