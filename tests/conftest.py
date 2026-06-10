#!/usr/bin/env python3
"""テスト用 conftest.py

セッションスコープの fixture と共通設定を提供する。
"""

from __future__ import annotations

import contextlib
import pathlib
import unittest.mock
from typing import TYPE_CHECKING

import my_lib.webapp.config
import pytest

if TYPE_CHECKING:
    from unit_cooler.config import Config

# URL プレフィックス設定
my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

# 設定ファイル
CONFIG_FILE = "config.example.yaml"
SCHEMA_CONFIG = "schema/config.schema"


def pytest_addoption(parser):
    """pytest コマンドラインオプションを追加"""
    parser.addoption("--host", default="127.0.0.1")
    parser.addoption("--port", default="5000")


# =============================================================================
# セッションスコープ fixture (高価、全テスト共有)
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def env_mock():
    """テスト環境変数の設定"""
    with unittest.mock.patch.dict(
        "os.environ",
        {
            "TEST": "true",
            "NO_COLORED_LOGS": "true",
        },
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session", autouse=True)
def slack_mock():
    """Slack API のモック"""
    with unittest.mock.patch(
        "my_lib.notify.slack.slack_sdk.web.client.WebClient.chat_postMessage",
        return_value={"ok": True, "ts": "1234567890.123456"},
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session")
def config() -> Config:
    """Config クラス形式の設定"""
    from unit_cooler.config import Config

    return Config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))


# =============================================================================
# 状態リセット fixture (各テスト前に自動実行)
# =============================================================================


@pytest.fixture(autouse=True)
def _clear(config):
    """各テスト前のクリーンアップ"""
    import sys

    import my_lib.footprint
    import my_lib.notify.slack
    import my_lib.webapp.log

    with unittest.mock.patch.dict("os.environ", {"DUMMY_MODE": "true"}):
        import unit_cooler.actuator.control
        import unit_cooler.actuator.valve_controller
        import unit_cooler.actuator.work_log

    liveness_files = [
        config.controller.liveness.file,
        config.actuator.subscribe.liveness.file,
        config.actuator.control.liveness.file,
        config.actuator.monitor.liveness.file,
        config.webui.subscribe.liveness.file,
    ]

    for liveness_file in liveness_files:
        my_lib.footprint.clear(liveness_file)

    unit_cooler.actuator.control.hazard_clear(config)
    with contextlib.suppress(RuntimeError):
        unit_cooler.actuator.valve_controller.get_valve_controller().clear_stat()
    unit_cooler.actuator.work_log.hist_clear()

    my_lib.webapp.log.term()

    my_lib.notify.slack._interval_clear()
    my_lib.notify.slack._hist_clear()

    # FD-Q10C モジュールをアンロードして状態をリセット
    if "my_lib.sensor.fd_q10c" in sys.modules:
        del sys.modules["my_lib.sensor.fd_q10c"]


@pytest.fixture(autouse=True)
def fluent_mock():
    """Fluent sender のモック"""
    with unittest.mock.patch("fluent.sender.FluentSender.emit") as fixture:

        def emit_mock(label, data):
            return True

        fixture.side_effect = emit_mock

        yield fixture
