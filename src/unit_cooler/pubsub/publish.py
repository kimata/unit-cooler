#!/usr/bin/env python3
"""
エアコン室外機の冷却モードの指示を出します。

Usage:
  publish.py [-c CONFIG] [-s SERVER_HOST] [-p SERVER_PORT] [-r REAL_PORT] [-n COUNT] [-t SPEEDUP] [-d] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -s SERVER_HOST    : サーバーのホスト名を指定します。 [default: localhost]
  -p SERVER_PORT    : ZeroMQ の サーバーを動作させるポートを指定します。 [default: 2222]
  -r REAL_PORT      : ZeroMQ の 本当のサーバーを動作させるポートを指定します。 [default: 2200]
  -n COUNT          : n 回制御メッセージを生成したら終了します。0 は制限なし。 [default: 1]
  -t SPEEDUP        : 時短モード。演算間隔を SPEEDUP 分の一にします。 [default: 20]
  -d                : ダミーモード(冷却モードをランダムに生成)で動作します。
  -D                : デバッグモードで動作します。
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import my_lib.json_util
import zmq

import unit_cooler.const

logger = logging.getLogger(__name__)


def wait_first_client(socket: zmq.Socket[bytes], timeout: float = 1.0) -> None:
    start_time = time.monotonic()

    logger.info("Waiting for first client connection...")
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    # タイムアウトに応じてポーリング間隔を調整
    poll_interval = min(100, int(timeout * 100))

    while True:
        events = dict(poller.poll(poll_interval))
        if socket in events:
            event = socket.recv()
            if event[0] == 1:  # 購読開始
                logger.info("First client connected.")
                # 購読イベントを処理
                socket.send(event)

        if time.monotonic() - start_time > timeout:
            logger.warning("Timeout waiting for first client connection.")
            break


def start_server(
    server_port: int,
    func: Callable[[], dict[str, Any]],
    interval_sec: float,
    msg_count: int = 0,
) -> None:
    logger.info("Start ZMQ server (port: %d)...", server_port)

    context = zmq.Context()

    socket = context.socket(zmq.XPUB)
    socket.bind(f"tcp://*:{server_port}")

    logger.info("Server initialize done.")

    # 最初のクライアント接続を待つ
    wait_first_client(socket)

    send_count = 0
    try:
        while True:
            # 購読イベントをチェック（ノンブロッキング）
            try:
                event = socket.recv(zmq.NOBLOCK)
                if event[0] == 0:  # 購読解除
                    logger.debug("Client unsubscribed.")
                elif event[0] == 1:  # 購読開始
                    logger.debug("New client subscribed.")
                # イベントを転送
                socket.send(event)
            except zmq.Again:
                pass  # イベントなし

            start_time = time.monotonic()
            socket.send_string(f"{unit_cooler.const.PUBSUB_CH} {my_lib.json_util.dumps(func())}")

            if msg_count != 0:
                send_count += 1
                logger.debug("(send_count, msg_count) = (%d, %d)", send_count, msg_count)
                # NOTE: Proxy が間に入るので、多く回す
                if send_count == (msg_count + 15):
                    logger.info("Terminate, because the specified number of times has been reached.")
                    break

            sleep_sec = max(interval_sec - (time.monotonic() - start_time), 0.5)
            logger.debug("Sleep %.1f sec...", sleep_sec)
            time.sleep(sleep_sec)
    except Exception:
        logger.exception("Server failed")

    socket.close()
    context.destroy()

    logger.warning("Stop ZMQ server")


# NOTE: Last Value Caching Proxy
# see https://zguide.zeromq.org/docs/chapter5/
def start_proxy(
    server_host: str,
    server_port: int,
    proxy_port: int,
    msg_count: int = 0,
    idle_timeout_sec: float = 0,
) -> None:
    """
    Last Value Caching Proxy を開始する。

    Args:
        server_host: サーバーホスト名
        server_port: サーバーポート（frontend）
        proxy_port: プロキシポート（backend）
        msg_count: 送信メッセージ数で終了（0=無制限）
        idle_timeout_sec: アイドルタイムアウト秒数（0=無制限）
                          subscribed=True になってからメッセージがない場合のタイムアウト
    """
    logger.info("Start ZMQ proxy server (front: %s:%d, port: %d)...", server_host, server_port, proxy_port)

    context = zmq.Context()

    frontend = context.socket(zmq.SUB)
    frontend.connect(f"tcp://{server_host}:{server_port}")
    frontend.setsockopt_string(zmq.SUBSCRIBE, unit_cooler.const.PUBSUB_CH)

    backend = context.socket(zmq.XPUB)
    backend.setsockopt(zmq.XPUB_VERBOSE, 1)
    backend.bind(f"tcp://*:{proxy_port}")

    cache = {}

    poller = zmq.Poller()
    poller.register(frontend, zmq.POLLIN)
    poller.register(backend, zmq.POLLIN)

    subscribed = False  # NOTE: テスト用
    proxy_count = 0
    idle_start_time = None  # アイドルタイムアウト計測用
    while True:
        try:
            events = dict(poller.poll(100))
        except KeyboardInterrupt:  # pragma: no cover
            break

        frontend_message_received = False
        if frontend in events:
            recv_data = frontend.recv_string()
            ch, json_str = recv_data.split(" ", 1)
            logger.debug("Store cache")
            cache[ch] = json_str

            logger.info("Proxy message")
            backend.send_string(recv_data)

            if subscribed:
                proxy_count += 1
            frontend_message_received = True

        if backend in events:
            logger.debug("Backend event")
            event = backend.recv()
            if event[0] == 0:
                logger.info("Client unsubscribed.")
            elif event[0] == 1:
                logger.info("New client subscribed.")
                subscribed = True
                ch = event[1:].decode("utf-8")
                if ch in cache:
                    logger.info("Send cache")
                    backend.send_string(f"{unit_cooler.const.PUBSUB_CH} {cache[unit_cooler.const.PUBSUB_CH]}")
                    proxy_count += 1
                else:
                    logger.warning("Cache is empty")
            else:  # pragma: no cover
                pass

        # アイドルタイムアウト処理（frontend からメッセージがない場合）
        # NOTE: subscribed がなくても、キャッシュがあれば（メッセージを受信済み）タイムアウトを有効にする
        if idle_timeout_sec > 0 and len(cache) > 0:
            if frontend_message_received:
                idle_start_time = None
            elif idle_start_time is None:
                idle_start_time = time.monotonic()
            elif time.monotonic() - idle_start_time > idle_timeout_sec:
                logger.info("Terminate due to idle timeout (%d sec).", idle_timeout_sec)
                break

        if msg_count != 0:
            logger.debug("(proxy_count, msg_count) = (%d, %d)", proxy_count, msg_count)
            if proxy_count == msg_count:
                logger.info("Terminate, because the specified number of times has been reached.")
                break

    frontend.close()
    backend.close()
    context.destroy()

    logger.warning("Stop ZMQ proxy server")


if __name__ == "__main__":
    # TEST Code
    import os
    import threading

    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    import unit_cooler.const
    import unit_cooler.controller.engine
    import unit_cooler.pubsub.subscribe

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    server_host = args["-s"]
    server_port = int(os.environ.get("HEMS_SERVER_PORT", args["-p"]))
    real_port = int(args["-r"])
    msg_count = int(args["-n"])
    speedup = int(args["-t"])
    dummy_mode = args["-d"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)

    proxy_thread = threading.Thread(
        target=start_proxy,
        args=(server_host, real_port, server_port, msg_count),
    )
    proxy_thread.start()

    server_thread = threading.Thread(
        target=start_server,
        args=(
            real_port,
            lambda: unit_cooler.controller.engine.gen_control_msg(config, dummy_mode, speedup).to_dict(),  # type: ignore[arg-type]
            config["controller"]["interval_sec"] / speedup,
            msg_count,
        ),
    )
    server_thread.start()

    unit_cooler.pubsub.subscribe.start_client(
        server_host,
        server_port,
        lambda message: logger.info("receive: %s", message),
        msg_count,
    )

    server_thread.join()
    proxy_thread.join()
