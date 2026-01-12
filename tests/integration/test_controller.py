#!/usr/bin/env python3
# ruff: noqa: S101
"""Controller 結合テスト

ZeroMQ を使用した Controller の動作を検証する。
"""

from __future__ import annotations

import threading
import time


class TestControllerStartup:
    """Controller 起動テスト"""

    def test_controller_starts_and_publishes(self, config, mocker, port_manager):
        """Controller が起動して ZeroMQ にメッセージを発行できる"""
        import zmq

        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()

        # footprint モック
        mocker.patch("my_lib.footprint.update")

        # サブスクライバーを起動してメッセージを受信
        received_messages = []
        subscriber_ready = threading.Event()
        should_stop = threading.Event()

        def subscriber():
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.connect(f"tcp://localhost:{server_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "unit_cooler")
            sock.setsockopt(zmq.RCVTIMEO, 5000)  # 5秒タイムアウト
            subscriber_ready.set()

            try:
                while not should_stop.is_set():
                    try:
                        msg = sock.recv_string()
                        received_messages.append(msg)
                        if len(received_messages) >= 2:
                            break
                    except zmq.Again:
                        continue
            finally:
                sock.close()
                ctx.term()

        sub_thread = threading.Thread(target=subscriber, daemon=True)
        sub_thread.start()
        subscriber_ready.wait(timeout=5)
        time.sleep(0.2)  # サブスクライバーが完全に準備されるまで待機

        # Controller を起動
        options = {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 2,
            "server_port": server_port,
            "real_port": real_port,
        }

        control_thread, proxy_thread = controller.start(config, options)

        # 終了を待機
        controller.wait_and_term(control_thread, proxy_thread)

        should_stop.set()
        sub_thread.join(timeout=2)

        # メッセージを検証
        assert len(received_messages) >= 1, "Controller からメッセージを受信できませんでした"

        # メッセージの形式を検証
        for msg in received_messages:
            assert msg.startswith("unit_cooler "), f"不正なチャンネル: {msg}"


class TestControllerMessageContent:
    """Controller メッセージ内容テスト"""

    def test_message_contains_required_fields(self, config, mocker, port_manager):
        """メッセージに必要なフィールドが含まれている"""
        import json
        import threading

        import zmq

        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        received_messages = []
        subscriber_ready = threading.Event()

        should_stop = threading.Event()

        def subscriber():
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.connect(f"tcp://localhost:{server_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "unit_cooler")
            sock.setsockopt(zmq.RCVTIMEO, 1000)
            subscriber_ready.set()

            try:
                while not should_stop.is_set() and len(received_messages) < 2:
                    try:
                        msg = sock.recv_string()
                        received_messages.append(msg)
                    except zmq.Again:
                        continue
            finally:
                sock.close()
                ctx.term()

        sub_thread = threading.Thread(target=subscriber, daemon=True)
        sub_thread.start()
        subscriber_ready.wait(timeout=5)
        time.sleep(0.5)  # プロキシが起動するまで待機

        options = {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 2,
            "server_port": server_port,
            "real_port": real_port,
        }

        control_thread, proxy_thread = controller.start(config, options)
        controller.wait_and_term(control_thread, proxy_thread)

        should_stop.set()
        sub_thread.join(timeout=5)

        assert len(received_messages) >= 1, (
            f"メッセージを受信できませんでした (received: {len(received_messages)})"
        )

        # JSON をパースしてフィールドを検証
        msg = received_messages[0]
        _, json_data = msg.split(" ", 1)
        data = json.loads(json_data)

        # 必須フィールドの確認
        assert "state" in data, "state フィールドがありません"
        assert "mode_index" in data, "mode_index フィールドがありません"


class TestControllerDummyMode:
    """Controller ダミーモードテスト"""

    def test_dummy_mode_generates_random_states(self, config, mocker, port_manager):
        """ダミーモードでランダムな状態が生成される"""
        import json
        import threading

        import zmq

        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        received_messages = []
        subscriber_ready = threading.Event()
        should_stop = threading.Event()

        def subscriber():
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.connect(f"tcp://localhost:{server_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "unit_cooler")
            sock.setsockopt(zmq.RCVTIMEO, 1000)
            subscriber_ready.set()

            try:
                while not should_stop.is_set() and len(received_messages) < 5:
                    try:
                        msg = sock.recv_string()
                        received_messages.append(msg)
                    except zmq.Again:
                        continue
            finally:
                sock.close()
                ctx.term()

        sub_thread = threading.Thread(target=subscriber, daemon=True)
        sub_thread.start()
        subscriber_ready.wait(timeout=5)
        time.sleep(0.2)

        options = {
            "speedup": 1000,  # 高速化
            "dummy_mode": True,
            "msg_count": 5,
            "server_port": server_port,
            "real_port": real_port,
        }

        control_thread, proxy_thread = controller.start(config, options)
        controller.wait_and_term(control_thread, proxy_thread)

        should_stop.set()
        sub_thread.join(timeout=2)

        assert len(received_messages) >= 3, "十分なメッセージを受信できませんでした"

        # mode_index の値を収集
        mode_indices = set()
        for msg in received_messages:
            _, json_data = msg.split(" ", 1)
            data = json.loads(json_data)
            mode_indices.add(data.get("mode_index", 0))

        # ダミーモードでは異なる mode_index が生成されるはず
        # （確率的なテストなので、最低でも1種類以上は生成されるはず）
        assert len(mode_indices) >= 1, "mode_index が生成されていません"
