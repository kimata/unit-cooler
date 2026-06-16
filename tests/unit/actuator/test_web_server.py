#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.actuator.web_server のテスト"""

from __future__ import annotations

import multiprocessing
from unittest.mock import MagicMock

import flask
import pytest

import unit_cooler.actuator.web_server


@pytest.fixture
def mock_webapp(mocker):
    """create_app の副作用（ログ初期化・イベント・メトリクス）をモックする"""
    mocker.patch("my_lib.webapp.config.build_environment")
    mocker.patch("my_lib.webapp.log.init")
    mocker.patch("my_lib.webapp.event.start")
    mocker.patch("unit_cooler.actuator.web_server.get_metrics_collector")


@pytest.mark.usefixtures("mock_webapp")
class TestCreateApp:
    """create_app のテスト"""

    def test_returns_flask_app_with_blueprints(self, config):
        """Flask アプリを生成し API ルートを登録する"""
        event_queue = multiprocessing.Queue()

        app = unit_cooler.actuator.web_server.create_app(config, event_queue)

        assert isinstance(app, flask.Flask)
        rules = {r.rule for r in app.url_map.iter_rules()}
        # 流量・バルブ状態 API が登録されていること
        assert any("get_flow" in r for r in rules)
        assert any("valve_status" in r for r in rules)

    def test_does_not_set_nonexistent_json_compat(self, config):
        """存在しない app.json.compat 属性を設定しない（typo 削除の回帰防止）"""
        event_queue = multiprocessing.Queue()

        app = unit_cooler.actuator.web_server.create_app(config, event_queue)

        assert not hasattr(app.json, "compat")


class TestStartTerm:
    """start / term のテスト"""

    def test_start_returns_handle_and_starts_thread(self, config, mocker):
        """start は WebServerHandle を返しサーバースレッドを開始する"""
        mock_app = MagicMock()
        mocker.patch("unit_cooler.actuator.web_server.create_app", return_value=mock_app)
        mock_server = MagicMock()
        mocker.patch("werkzeug.serving.make_server", return_value=mock_server)

        event_queue = multiprocessing.Queue()
        handle = unit_cooler.actuator.web_server.start(config, event_queue, 5901)

        assert isinstance(handle, unit_cooler.actuator.web_server.WebServerHandle)
        assert handle.server is mock_server
        # サーバースレッドが生成され serve_forever が呼ばれること
        handle.thread.join(timeout=5)
        mock_server.serve_forever.assert_called()

    def test_term_shuts_down_server(self, mocker):
        """term はサーバーを停止しスレッドを join する"""
        mocker.patch("my_lib.webapp.event.term")
        mocker.patch("my_lib.webapp.log.term")

        mock_server = MagicMock()
        mock_thread = MagicMock()
        handle = unit_cooler.actuator.web_server.WebServerHandle(server=mock_server, thread=mock_thread)

        unit_cooler.actuator.web_server.term(handle)

        mock_server.shutdown.assert_called_once()
        mock_server.server_close.assert_called_once()
        mock_thread.join.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
