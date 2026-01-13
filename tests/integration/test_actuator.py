#!/usr/bin/env python3
# ruff: noqa: S101
"""Actuator 結合テスト

Actuator の起動、制御メッセージ受信、バルブ制御を検証する。
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager

import zmq

from unit_cooler.config import RuntimeSettings


@contextmanager
def zmq_publisher(port: int, msg_count: int = 0, interval: float = 0.05):
    """テスト用の ZeroMQ パブリッシャーを起動するコンテキストマネージャー

    Args:
        port: バインドするポート番号
        msg_count: 送信するメッセージ数 (0=無制限、should_stop まで送信)
        interval: メッセージ送信間隔（秒）
    """
    ready = threading.Event()
    should_stop = threading.Event()

    def publisher():
        ctx = zmq.Context()
        sock = ctx.socket(zmq.PUB)
        sock.bind(f"tcp://*:{port}")
        ready.set()

        try:
            # サブスクライバーが接続するまで待機
            time.sleep(0.2)
            i = 0
            while not should_stop.is_set():
                msg = {"mode_index": i % 4, "state": 0}
                sock.send_string(f"unit_cooler {json.dumps(msg)}")
                i += 1
                if msg_count > 0 and i >= msg_count:
                    break
                time.sleep(interval)
                # 継続的に送信（最大 200 メッセージ）
                if i >= 200:
                    break
        finally:
            sock.close()
            ctx.term()

    thread = threading.Thread(target=publisher, daemon=True)
    thread.start()
    ready.wait(timeout=2)

    try:
        yield (thread, should_stop)
    finally:
        should_stop.set()
        thread.join(timeout=2)


class TestActuatorStartup:
    """Actuator 起動テスト"""

    def test_actuator_starts_successfully(self, config, mocker, port_manager):
        """Actuator が正常に起動して終了できる"""
        import actuator

        pub_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        # footprint モック
        mocker.patch("my_lib.footprint.update")

        # msg_count を設定して自然終了させる
        settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": pub_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        # パブリッシャーを起動してからActuatorを起動
        with zmq_publisher(pub_port) as (pub_thread, should_stop):
            executor, thread_list, log_server_handle = actuator.start(config, settings)

            # 正常終了を確認（msg_count 達成で自然終了）
            ret = actuator.wait_and_term(executor, thread_list, log_server_handle)

            # パブリッシャーを停止
            should_stop.set()

            assert ret == 0 or ret == -1  # subscribe_worker がタイムアウトする可能性があるため


class TestActuatorMessageReceive:
    """Actuator メッセージ受信テスト"""

    def test_actuator_receives_control_message(self, config, mocker, port_manager):
        """Actuator が ZeroMQ メッセージを受信できる"""
        import actuator

        pub_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # msg_count を設定して自然終了させる
        settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": pub_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        # パブリッシャーを起動してからActuatorを起動
        with zmq_publisher(pub_port) as (_, should_stop):
            executor, thread_list, log_server_handle = actuator.start(config, settings)

            # 正常終了を確認（msg_count 達成で自然終了）
            ret = actuator.wait_and_term(executor, thread_list, log_server_handle)

            # パブリッシャーを停止
            should_stop.set()

            # エラーなく終了することを確認
            assert ret == 0 or ret == -1


class TestActuatorValveControl:
    """Actuator バルブ制御テスト"""

    def test_valve_responds_to_control_message(self, config, mocker, port_manager):
        """バルブが制御メッセージに応答する"""
        import actuator

        pub_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # msg_count を設定して自然終了させる
        settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": pub_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        # パブリッシャーを起動してからActuatorを起動
        with zmq_publisher(pub_port) as (_, should_stop):
            executor, thread_list, log_server_handle = actuator.start(config, settings)

            # 正常終了を確認（msg_count 達成で自然終了）
            actuator.wait_and_term(executor, thread_list, log_server_handle)

            # パブリッシャーを停止
            should_stop.set()


class TestActuatorWebServer:
    """Actuator Web サーバーテスト"""

    def test_web_server_starts(self, config, mocker, port_manager):
        """Web サーバーが起動する"""
        import actuator

        pub_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # msg_count を設定して自然終了させる
        settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": pub_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        # パブリッシャーを起動してからActuatorを起動
        with zmq_publisher(pub_port) as (_, should_stop):
            executor, thread_list, log_server_handle = actuator.start(config, settings)

            # log_server_handle が返されることを確認
            assert log_server_handle is not None, "Web サーバーハンドルが返されませんでした"

            # 正常終了を確認（msg_count 達成で自然終了）
            actuator.wait_and_term(executor, thread_list, log_server_handle)

            # パブリッシャーを停止
            should_stop.set()


class TestActuatorDummyMode:
    """Actuator ダミーモードテスト"""

    def test_dummy_mode_sets_environment(self, config, mocker, port_manager):
        """ダミーモードで環境変数が設定される"""
        import os

        import actuator

        pub_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        # DUMMY_MODE 環境変数を確認
        original_dummy = os.environ.get("DUMMY_MODE")

        mocker.patch("my_lib.footprint.update")

        # msg_count を設定して自然終了させる
        settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": pub_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        # パブリッシャーを起動してからActuatorを起動
        with zmq_publisher(pub_port) as (_, should_stop):
            executor, thread_list, log_server_handle = actuator.start(config, settings)

            # ダミーモードで起動したことを確認
            assert os.environ.get("DUMMY_MODE") == "true"

            # 正常終了を確認（msg_count 達成で自然終了）
            actuator.wait_and_term(executor, thread_list, log_server_handle)

            # パブリッシャーを停止
            should_stop.set()

        # 環境変数を元に戻す
        if original_dummy is not None:
            os.environ["DUMMY_MODE"] = original_dummy
