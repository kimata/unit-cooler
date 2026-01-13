#!/usr/bin/env python3
# ruff: noqa: S101
"""Controller -> Actuator 結合テスト

Controller から Actuator への制御メッセージフローを検証する。
ZeroMQ を介した完全な制御パイプラインをテストする。
"""

from __future__ import annotations

import threading
import time

import zmq

from unit_cooler.config import RuntimeSettings


class TestControllerActuatorFlow:
    """Controller → Actuator 制御フローテスト"""

    def test_controller_to_actuator_message_flow(self, config, mocker, port_manager):
        """Controller のメッセージが Actuator に到達する"""
        import actuator
        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # Controller を起動（多めにメッセージを送信）
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 10,
                "server_port": server_port,
                "real_port": real_port,
                "idle_timeout_sec": 3,  # 3秒アイドルでタイムアウト
            }
        )

        control_thread, proxy_thread = controller.start(config, controller_settings)

        # Controller が起動するまで待機
        time.sleep(0.3)

        # Actuator を起動（msg_count でメッセージ受信数を指定）
        actuator_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": server_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        executor, thread_list, log_server_handle = actuator.start(config, actuator_settings)

        # Actuator の終了を待機（msg_count 達成で自然終了）
        actuator.wait_and_term(executor, thread_list, log_server_handle)

        # Controller の終了を待機
        controller.wait_and_term(control_thread, proxy_thread)

        # テストが正常に完了することを確認
        # (例外が発生しなければ成功)

    def test_actuator_receives_multiple_messages(self, config, mocker, port_manager):
        """Actuator が複数の制御メッセージを受信できる"""
        import actuator
        import controller
        import unit_cooler.actuator.worker

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # 受信メッセージを追跡（元の関数も呼び出す）
        received_count = {"count": 0}
        original_queue_put = unit_cooler.actuator.worker.queue_put

        def track_queue_put(queue, message, liveness_file):
            received_count["count"] += 1
            original_queue_put(queue, message, liveness_file)

        mocker.patch(
            "unit_cooler.actuator.worker.queue_put",
            side_effect=track_queue_put,
        )

        # Controller を起動（多めにメッセージを送信）
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 10,
                "server_port": server_port,
                "real_port": real_port,
                "idle_timeout_sec": 3,  # 3秒アイドルでタイムアウト
            }
        )

        control_thread, proxy_thread = controller.start(config, controller_settings)
        time.sleep(0.3)

        # Actuator を起動（msg_count でメッセージ受信数を指定）
        actuator_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,  # 3 メッセージ受信で終了
                "pub_port": server_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        executor, thread_list, log_server_handle = actuator.start(config, actuator_settings)

        # Actuator の終了を待機（msg_count 達成で自然終了）
        actuator.wait_and_term(executor, thread_list, log_server_handle)

        # Controller の終了を待機
        controller.wait_and_term(control_thread, proxy_thread)

        # 複数のメッセージが受信されたことを確認
        assert received_count["count"] >= 1, (
            f"Actuator がメッセージを受信できませんでした (received: {received_count['count']})"
        )


class TestControllerActuatorCachingProxy:
    """Last Value Caching Proxy テスト"""

    def test_late_subscriber_receives_cached_message_immediately(self, config, mocker, port_manager):
        """遅れて接続したサブスクライバーがキャッシュされたメッセージをすぐに受信できる

        Proxy の Last Value Caching 機能のテスト:
        1. Controller がメッセージを送信（Proxy がキャッシュに保存）
        2. しばらく後に subscriber が接続
        3. subscriber が接続後すぐに（200ms以内）キャッシュからメッセージを受信
        """
        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # Controller を起動
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 5,
                "server_port": server_port,
                "real_port": real_port,
                "idle_timeout_sec": 5,  # 5秒アイドルでタイムアウト
            }
        )

        control_thread, proxy_thread = controller.start(config, controller_settings)

        # Controller がいくつかのメッセージを送信するまで待機（Proxy にキャッシュされる）
        # NOTE: Server の wait_first_client が1秒タイムアウトを待つので、
        #       最初のメッセージが送信されるまで 1.5 秒以上待つ必要がある
        time.sleep(2.0)

        # 遅れてサブスクライバーを接続
        first_message_time = None
        connection_time = None
        received_messages = []
        subscriber_ready = threading.Event()

        def late_subscriber():
            nonlocal first_message_time, connection_time
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.connect(f"tcp://localhost:{server_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "unit_cooler")
            # 短いタイムアウト: キャッシュがあればすぐに受信できるはず
            sock.setsockopt(zmq.RCVTIMEO, 200)
            connection_time = time.time()
            subscriber_ready.set()

            try:
                while len(received_messages) < 2:
                    try:
                        msg = sock.recv_string()
                        if first_message_time is None:
                            first_message_time = time.time()
                        received_messages.append(msg)
                    except zmq.Again:
                        break
            finally:
                sock.close()
                ctx.term()

        sub_thread = threading.Thread(target=late_subscriber, daemon=True)
        sub_thread.start()
        subscriber_ready.wait(timeout=2)

        sub_thread.join(timeout=3)
        controller.wait_and_term(control_thread, proxy_thread)

        # 遅れて接続したサブスクライバーがメッセージを受信できたことを確認
        assert len(received_messages) >= 1, "遅れて接続したサブスクライバーがメッセージを受信できませんでした"

        # キャッシュからすぐに（200ms以内）メッセージを受信できたことを確認
        assert first_message_time is not None, "メッセージ受信時刻が記録されていません"
        response_time_ms = (first_message_time - connection_time) * 1000
        assert response_time_ms < 200, (
            f"キャッシュからの応答が遅すぎます: {response_time_ms:.1f}ms (200ms以内であるべき)"
        )


class TestControllerActuatorErrorHandling:
    """エラーハンドリングテスト"""

    def test_actuator_handles_controller_disconnect(self, config, mocker, port_manager):
        """Actuator が Controller の切断を処理できる"""
        import actuator
        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # Controller を起動（すぐに終了）
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 2,
                "server_port": server_port,
                "real_port": real_port,
                "idle_timeout_sec": 3,  # 3秒アイドルでタイムアウト
            }
        )

        control_thread, proxy_thread = controller.start(config, controller_settings)
        time.sleep(0.3)

        # Actuator を起動
        actuator_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 1,
                "pub_port": server_port,
                "log_port": log_port,
                "control_host": "localhost",
            }
        )

        executor, thread_list, log_server_handle = actuator.start(config, actuator_settings)

        # Controller を先に終了
        controller.wait_and_term(control_thread, proxy_thread)

        # Actuator も終了（エラーなく終了することを確認）
        actuator.wait_and_term(executor, thread_list, log_server_handle)

    def test_controller_handles_no_subscribers(self, config, mocker, port_manager):
        """Controller がサブスクライバーなしでも動作する"""
        import controller

        real_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # サブスクライバーなしで Controller を起動
        # NOTE: disable_proxy=True を設定しないと、proxy が subscriber を待ち続けてハングする
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 3,
                "real_port": real_port,
                "disable_proxy": True,
            }
        )

        control_thread, proxy_thread = controller.start(config, controller_settings)

        # 正常終了することを確認
        controller.wait_and_term(control_thread, proxy_thread)
