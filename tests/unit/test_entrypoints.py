#!/usr/bin/env python3
# ruff: noqa: S101
"""エントリポイント（controller.py / actuator.py / webui.py）のテスト"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock

import flask
import pytest


class TestController:
    """controller.py のテスト"""

    def test_gen_control_msg_returns_dict(self, config, mocker):
        """gen_control_msg は制御メッセージを dict で返し liveness を更新する"""
        import controller

        mock_msg = MagicMock()
        mock_msg.to_dict.return_value = {"mode_index": 2}
        mocker.patch("unit_cooler.controller.engine.gen_control_msg", return_value=mock_msg)
        mock_footprint = mocker.patch("my_lib.footprint.update")

        result = controller.gen_control_msg(config, dummy_mode=True, speedup=10)

        assert result == {"mode_index": 2}
        mock_footprint.assert_called_once_with(config.controller.liveness.file)

    def test_cache_proxy_start_launches_thread(self, mocker):
        """cache_proxy_start は start_proxy をスレッドで起動する"""
        import controller

        mock_proxy = mocker.patch("unit_cooler.pubsub.publish.start_proxy")

        thread = controller.cache_proxy_start("localhost", 2200, 2222, msg_count=1)
        thread.join(timeout=5)

        assert not thread.is_alive()
        mock_proxy.assert_called_once()

    def test_control_server_start_launches_thread(self, config, mocker):
        """control_server_start は start_server をスレッドで起動する"""
        import controller

        mock_server = mocker.patch("unit_cooler.pubsub.publish.start_server")

        thread = controller.control_server_start(config, 2200, dummy_mode=True, speedup=10, msg_count=1)
        thread.join(timeout=5)

        assert not thread.is_alive()
        mock_server.assert_called_once()


class TestActuator:
    """actuator.py のテスト"""

    def test_wait_before_start_sleeps_interval(self, config, mocker):
        """wait_before_start は interval_sec 回 sleep する"""
        import actuator

        mock_sleep = mocker.patch("actuator.time.sleep")

        actuator.wait_before_start(config)

        assert mock_sleep.call_count == config.actuator.control.interval_sec

    def test_sig_handler_terminates_on_sigterm(self, mocker):
        """SIGTERM 受信でワーカーを終了させる"""
        import actuator

        mock_term = mocker.patch("unit_cooler.actuator.worker.term")

        actuator.sig_handler(signal.SIGTERM, None)

        mock_term.assert_called_once()

    def test_sig_handler_ignores_other_signals(self, mocker):
        """対象外シグナルでは終了処理を行わない"""
        import actuator

        mock_term = mocker.patch("unit_cooler.actuator.worker.term")

        actuator.sig_handler(signal.SIGUSR1, None)

        mock_term.assert_not_called()


class TestWebui:
    """webui.py のテスト"""

    def test_create_app_returns_flask_app(self, config, mocker):
        """create_app は購読ワーカーを起動しつつ Flask アプリを返す"""
        import webui
        from unit_cooler.config import RuntimeSettings

        mocker.patch("my_lib.webapp.config.build_environment")
        mocker.patch("my_lib.webapp.proxy.init")
        # ZMQ 購読ワーカーは起動せず即終了させる
        mock_worker = mocker.patch("unit_cooler.webui.worker.subscribe_worker")

        settings = RuntimeSettings.from_dict(
            {
                "msg_count": 1,
                "dummy_mode": True,
                "pub_port": 2222,
                "log_port": 5001,
                "status_pub_port": 0,
            }
        )

        app = webui.create_app(config, settings)

        assert isinstance(app, flask.Flask)
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert any("stat" in r for r in rules)
        # 購読ワーカースレッドが 1 度起動されること
        mock_worker.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
