#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import logging
import queue
import time
import traceback
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import my_lib.json_util
import zmq

import unit_cooler.const
import unit_cooler.util
from unit_cooler.messages import ControlMessage

logger = logging.getLogger(__name__)

# 受信がこの秒数途絶えたら SUB ソケットを作り直して再接続する。
# Publisher 側ノードの突然死（電源断等）では FIN/RST が届かず、SUB は自分からは
# 何も送信しないため、ハーフオープン接続を掴んだまま永遠に受信できなくなる。
# Controller の配信間隔（60 秒）の 3 倍を目安とする。
RECONNECT_TIMEOUT_SEC = 180

if TYPE_CHECKING:
    import pathlib
    import threading
    from collections.abc import Callable
    from multiprocessing import Queue

    from unit_cooler.config import Config

    # NOTE: actuator は multiprocessing.Queue、webui はスレッド内完結のため queue.Queue を使う
    MessageQueue = Queue[ControlMessage] | queue.Queue[ControlMessage]


def create_subscriber(context: zmq.Context, host: str, port: int, topic: str) -> zmq.Socket:
    """死活検知付きの SUB ソケットを作成して接続する

    NOTE: Publisher ノードの突然死では FIN/RST が届かないため、TCP keepalive と
    ZMTP heartbeat でカーネル / ZeroMQ レベルでも切断を検知・再接続させる。
    """
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
    socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 60)
    socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 10)
    socket.setsockopt(zmq.TCP_KEEPALIVE_CNT, 3)
    socket.setsockopt(zmq.HEARTBEAT_IVL, 10 * 1000)
    socket.setsockopt(zmq.HEARTBEAT_TIMEOUT, 30 * 1000)
    # ノンブロッキング受信のためにタイムアウトを設定（終了フラグ確認用）
    socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒タイムアウト
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(f"tcp://{host}:{port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, topic)
    return socket


def start_client(
    server_host: str,
    server_port: int,
    func: Callable[[dict[str, Any]], None],
    msg_count: int = 0,
    should_terminate: threading.Event | None = None,
) -> None:
    logger.info("Start ZMQ client...")

    context = zmq.Context()
    socket = create_subscriber(context, server_host, server_port, unit_cooler.const.PUBSUB_CH)

    logger.info("Client initialize done.")

    receive_count = 0
    last_recv_time = time.monotonic()
    while True:
        # 終了フラグをチェック
        if should_terminate and should_terminate.is_set():
            logger.info("Terminate signal received, stopping ZMQ client")
            break

        try:
            raw_message = socket.recv_string()
        except zmq.Again:
            # タイムアウト時: 受信が長時間途絶えていたらソケットを作り直す
            # （ハーフオープン接続を掴んだままだと自然回復しないため）
            if time.monotonic() - last_recv_time > RECONNECT_TIMEOUT_SEC:
                logger.warning(
                    "No message received for %.0f sec, recreating socket...",
                    time.monotonic() - last_recv_time,
                )
                socket.close()
                socket = create_subscriber(context, server_host, server_port, unit_cooler.const.PUBSUB_CH)
                last_recv_time = time.monotonic()
            continue

        last_recv_time = time.monotonic()

        # NOTE: 不正なメッセージ 1 通でワーカーが止まらないよう、
        # メッセージ単位で例外を処理してスキップする
        try:
            _, json_str = raw_message.split(" ", 1)
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

    socket.close()
    context.destroy()


def queue_put(
    message_queue: MessageQueue,
    message: dict[str, Any],
    liveness_file: pathlib.Path,
    drop_oldest: bool = False,
) -> None:
    """受信メッセージを ControlMessage に変換してキューに積む"""
    control_message = ControlMessage.from_dict(message)

    if drop_oldest and message_queue.full():
        # NOTE: full() チェックと get() の間に消費側がキューを空にすると
        # ブロッキング get() で凍結する（TOCTOU）ため、get_nowait() で空振りを許容する
        with contextlib.suppress(queue.Empty):
            message_queue.get_nowait()

    logger.debug("Receive message: %s", control_message)

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
