#!/usr/bin/env python3
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import my_lib.json_util
import zmq

import unit_cooler.const

logger = logging.getLogger(__name__)


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
            ch, json_str = socket.recv_string().split(" ", 1)
            json_data = my_lib.json_util.loads(json_str)
            logger.debug("recv %s", json_data)
            func(json_data)

            if msg_count != 0:
                receive_count += 1
                logger.debug("(receive_count, msg_count) = (%d, %d)", receive_count, msg_count)
                if receive_count == msg_count:
                    logger.info("Terminate, because the specified number of times has been reached.")
                    break
        except zmq.Again:
            # タイムアウト時は継続してループを回す
            continue

    logging.warning("Stop ZMQ client")

    socket.disconnect(target)
    socket.close()
    context.destroy()
