#!/usr/bin/env python3
from __future__ import annotations

import logging
import pathlib
import threading
import traceback
from typing import TYPE_CHECKING, Any

import my_lib.footprint

import unit_cooler.const
import unit_cooler.pubsub.subscribe
import unit_cooler.util

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

# グローバル終了フラグ
should_terminate = threading.Event()


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
def subscribe_worker(  # noqa: PLR0913
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
