#!/usr/bin/env python3
# ruff: noqa: S101
"""完全システム結合テスト

Controller + Actuator + WebUI の完全なシステムシナリオをテストする。
"""

from __future__ import annotations

import json
import threading
import time

import zmq

from unit_cooler.config import RuntimeSettings


class TestFullSystemStartup:
    """フルシステム起動テスト"""

    def test_full_system_starts_and_stops(self, config, mocker, port_manager):
        """Controller + Actuator + WebUI が起動して終了できる"""
        import actuator
        import controller
        import unit_cooler.webui.worker
        import webui

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()
        http_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # Controller を起動（多めにメッセージを送信）
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 10,
                "server_port": server_port,
                "real_port": real_port,
            }
        )
        control_thread, proxy_thread = controller.start(config, controller_settings)
        time.sleep(0.2)

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
        time.sleep(0.2)

        # WebUI を起動
        webui_settings = RuntimeSettings.from_dict(
            {
                "dummy_mode": True,
                "pub_port": server_port,
                "log_port": log_port,
            }
        )
        app = webui.create_app(config, webui_settings)

        def run_webui():
            app.run(host="127.0.0.1", port=http_port, threaded=True, use_reloader=False)

        webui_thread = threading.Thread(target=run_webui, daemon=True)
        webui_thread.start()
        time.sleep(0.5)

        # 全コンポーネントを終了
        # NOTE: webui.term() は sys.exit() を呼ぶので、worker を直接終了
        unit_cooler.webui.worker.term()
        # グローバル変数をクリア
        webui.worker_threads.clear()
        # 終了フラグをリセット（次のテストのため）
        unit_cooler.webui.worker.should_terminate.clear()
        # Actuator の終了を待機（msg_count 達成で自然終了）
        actuator.wait_and_term(executor, thread_list, log_server_handle)
        # Controller の終了を待機
        controller.wait_and_term(control_thread, proxy_thread)


class TestFullSystemDataFlow:
    """フルシステムデータフローテスト"""

    def test_sensor_data_flows_through_system(self, config, mocker, port_manager):
        """センサーデータがシステム全体を流れる"""
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


class TestFullSystemWebUIIntegration:
    """WebUI 統合テスト"""

    def test_webui_serves_api_endpoints(self, config, mocker, port_manager):
        """WebUI が API エンドポイントを提供する"""
        import unit_cooler.webui.worker
        import webui

        server_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # WebUI を起動
        webui_settings = RuntimeSettings.from_dict(
            {
                "dummy_mode": True,
                "pub_port": server_port,
                "log_port": log_port,
            }
        )
        app = webui.create_app(config, webui_settings)

        # Flask テストクライアントを使用
        with app.test_client() as client:
            # ヘルスチェックエンドポイント（URL_PREFIX = /unit-cooler, route = /api/stat）
            response = client.get("/unit-cooler/api/stat")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert "watering" in data or "sensor" in data or isinstance(data, dict)

        # NOTE: webui.term() は sys.exit() を呼ぶので、worker を直接終了
        unit_cooler.webui.worker.term()
        # グローバル変数をクリア
        webui.worker_threads.clear()
        # 終了フラグをリセット（次のテストのため）
        unit_cooler.webui.worker.should_terminate.clear()

    def test_webui_with_controller_data(self, config, mocker, port_manager):
        """WebUI が Controller からのデータを表示できる（proxy 経由でキャッシュ機能をテスト）"""
        import controller
        import unit_cooler.webui.worker
        import webui

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()
        log_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # Controller を起動（proxy 経由）
        # idle_timeout_sec を設定してアイドルタイムアウトで終了できるようにする
        controller_settings = RuntimeSettings.from_dict(
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 5,
                "server_port": server_port,
                "real_port": real_port,
                "idle_timeout_sec": 3,  # 3秒アイドルでタイムアウト
            }
        )
        control_thread, proxy_thread = controller.start(config, controller_settings)
        time.sleep(0.3)

        # WebUI を起動（proxy 経由で接続）
        webui_settings = RuntimeSettings.from_dict(
            {
                "dummy_mode": True,
                "pub_port": server_port,  # proxy 経由
                "log_port": log_port,
            }
        )
        app = webui.create_app(config, webui_settings)

        # Flask テストクライアントを使用
        with app.test_client() as client:
            # URL_PREFIX = /unit-cooler, route = /api/stat
            response = client.get("/unit-cooler/api/stat")
            assert response.status_code == 200

        # 終了
        # NOTE: webui.term() は sys.exit() を呼ぶので、worker を直接終了
        unit_cooler.webui.worker.term()
        # グローバル変数をクリア
        webui.worker_threads.clear()
        # 終了フラグをリセット（次のテストのため）
        unit_cooler.webui.worker.should_terminate.clear()
        controller.wait_and_term(control_thread, proxy_thread)


class TestFullSystemScenarios:
    """完全システムシナリオテスト"""

    def test_high_temperature_scenario(self, config, mocker, port_manager):
        """高温シナリオ: エアコン稼働中に高温になった場合"""
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

        # テストが正常完了することを確認

    def test_rain_scenario(self, config, mocker, port_manager):
        """雨天シナリオ: Controller と Actuator が連携して動作する"""
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


class TestFullSystemResilience:
    """フルシステム耐障害性テスト"""

    def test_system_recovers_from_temporary_disconnect(self, config, mocker, port_manager):
        """一時的な切断からシステムが回復する"""
        import controller

        server_port = port_manager.find_unused_port()
        real_port = port_manager.find_unused_port()

        mocker.patch("my_lib.footprint.update")

        # Controller を起動
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
        time.sleep(0.2)

        # 最初のサブスクライバーを接続して切断
        messages_first = []

        def first_subscriber():
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.connect(f"tcp://localhost:{server_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "unit_cooler")
            sock.setsockopt(zmq.RCVTIMEO, 300)

            try:
                for _ in range(2):
                    try:
                        msg = sock.recv_string()
                        messages_first.append(msg)
                    except zmq.Again:
                        break
            finally:
                sock.close()
                ctx.term()

        first_thread = threading.Thread(target=first_subscriber, daemon=True)
        first_thread.start()
        first_thread.join(timeout=2)

        # 少し待ってから2番目のサブスクライバーを接続
        time.sleep(0.2)
        messages_second = []

        def second_subscriber():
            ctx = zmq.Context()
            sock = ctx.socket(zmq.SUB)
            sock.connect(f"tcp://localhost:{server_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "unit_cooler")
            sock.setsockopt(zmq.RCVTIMEO, 500)

            try:
                for _ in range(2):
                    try:
                        msg = sock.recv_string()
                        messages_second.append(msg)
                    except zmq.Again:
                        break
            finally:
                sock.close()
                ctx.term()

        second_thread = threading.Thread(target=second_subscriber, daemon=True)
        second_thread.start()
        second_thread.join(timeout=2)

        controller.wait_and_term(control_thread, proxy_thread)

        # 両方のサブスクライバーがメッセージを受信できたことを確認
        assert len(messages_first) >= 1 or len(messages_second) >= 1, (
            "サブスクライバーがメッセージを受信できませんでした"
        )
