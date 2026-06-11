#!/usr/bin/env python3
from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import my_lib.json_util
import zmq

import unit_cooler.const
import unit_cooler.util
from unit_cooler.messages import ControlMessage

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib
    import threading
    from collections.abc import Callable
    from multiprocessing import Queue

    from unit_cooler.config import Config


def start_client(
    server_host: str,
    server_port: int,
    func: Callable[[dict[str, Any]], None],
    msg_count: int = 0,
    should_terminate: threading.Event | None = None,
) -> None:
    logger.info("Start ZMQ client...")

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    target = f"tcp://{server_host}:{server_port}"
    socket.connect(target)
    socket.setsockopt_string(zmq.SUBSCRIBE, unit_cooler.const.PUBSUB_CH)

    # ノンブロッキング受信のためにタイムアウトを設定
    socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒タイムアウト

    logger.info("Client initialize done.")

    receive_count = 0
    while True:
        # 終了フラグをチェック
        if should_terminate and should_terminate.is_set():
            logger.info("Terminate signal received, stopping ZMQ client")
            break

        try:
            raw_message = socket.recv_string()
        except zmq.Again:
            # タイムアウト時は継続してループを回す
            continue

        # NOTE: 不正なメッセージ 1 通でワーカーが止まらないよう、
        # メッセージ単位で例外を処理してスキップする
        try:
            ch, json_str = raw_message.split(" ", 1)
            json_data = my_lib.json_util.loads(json_str)
            logger.debug("recv %s", json_data)
            func(json_data)
        except Exception:
            logger.exception("Failed to process received message, skipping")
            continue

        if msg_count != 0:
            receive_count += 1
            logger.debug("(receive_count, msg_count) = (%d, %d)", receive_count, msg_count)
            if receive_count == msg_count:
                logger.info("Terminate, because the specified number of times has been reached.")
                break

    logger.warning("Stop ZMQ client")

    socket.disconnect(target)
    socket.close()
    context.destroy()


def queue_put(
    message_queue: Queue[ControlMessage],
    message: dict[str, Any],
    liveness_file: pathlib.Path,
    drop_oldest: bool = False,
) -> None:
    """受信メッセージを ControlMessage に変換してキューに積む"""
    control_message = ControlMessage.from_dict(message)

    if drop_oldest and message_queue.full():
        message_queue.get()

    logger.info("Receive message: %s", control_message)

    message_queue.put(control_message)
    my_lib.footprint.update(liveness_file)


def run_subscribe_worker(
    config: Config,
    name: str,
    control_host: str,
    pub_port: int,
    func: Callable[[dict[str, Any]], None],
    msg_count: int = 0,
    should_terminate: threading.Event | None = None,
) -> int:
    """制御メッセージを購読してコールバックに渡すワーカーの共通実装"""
    logger.info("Start %s subscribe worker (%s:%d)", name, control_host, pub_port)

    ret = 0
    try:
        start_client(control_host, pub_port, func, msg_count, should_terminate)
    except Exception:
        logger.exception("Failed to receive control message")
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1

    logger.warning("Stop %s subscribe worker", name)
    return ret
