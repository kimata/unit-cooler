#!/usr/bin/env python3
"""テスト用 conftest.py

セッションスコープの fixture と共通設定を提供する。
"""

from __future__ import annotations

import os
import pathlib
import unittest.mock
from typing import TYPE_CHECKING

import my_lib.webapp.config
import pytest

# ヘルパーモジュールのインポート
from tests.helpers import (
    ComponentManager,
    PortManager,
    find_unused_port,
    release_port,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from unit_cooler.config import Config

# URL プレフィックス設定
my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

# 設定ファイル
CONFIG_FILE = "config.example.yaml"
SCHEMA_CONFIG = "config.schema"


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
def raw_config():
    """辞書形式の設定（互換性用）"""
    import my_lib.config

    return my_lib.config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))


@pytest.fixture(scope="session")
def config(raw_config) -> Config:
    """Config クラス形式の設定"""
    from unit_cooler.config import Config

    return Config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))


# =============================================================================
# ポート管理 fixture
# =============================================================================


@pytest.fixture(scope="session")
def port_manager() -> Generator[PortManager, None, None]:
    """セッションスコープのポートマネージャー"""
    manager = PortManager()
    # テスト開始前に古いポート情報をクリーンアップ
    PortManager.cleanup_stale_ports()
    yield manager
    # テスト終了時に割り当てたポートを解放
    manager.release_all()


@pytest.fixture
def server_port() -> Generator[int, None, None]:
    """ZeroMQ サーバーポート"""
    port = find_unused_port()
    yield port
    release_port(port)


@pytest.fixture
def real_port() -> Generator[int, None, None]:
    """実サーバーポート"""
    port = find_unused_port()
    yield port
    release_port(port)


@pytest.fixture
def log_port() -> Generator[int, None, None]:
    """ログサーバーポート"""
    port = find_unused_port()
    yield port
    release_port(port)


# =============================================================================
# 状態リセット fixture (各テスト前に自動実行)
# =============================================================================


@pytest.fixture(autouse=True)
def reset_state_manager_fixture():
    """各テストの前後で StateManager をリセット"""
    from unit_cooler.state_manager import reset_state_manager

    reset_state_manager()
    yield
    reset_state_manager()


@pytest.fixture(autouse=True)
def _clear(config):
    """各テスト前のクリーンアップ"""
    import sys

    import my_lib.footprint
    import my_lib.notify.slack
    import my_lib.webapp.log

    with unittest.mock.patch.dict("os.environ", {"DUMMY_MODE": "true"}):
        import unit_cooler.actuator.control
        import unit_cooler.actuator.valve
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
    unit_cooler.actuator.valve.clear_stat()
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


# =============================================================================
# コンポーネント管理 fixture
# =============================================================================


@pytest.fixture
def new_component_manager() -> Generator[ComponentManager, None, None]:
    """新しい ComponentManager を提供"""
    manager = ComponentManager()
    yield manager
    manager.teardown_all()


# =============================================================================
# Playwright 関連 fixture
# =============================================================================


def pytest_addoption(parser):
    """pytest コマンドラインオプションを追加"""
    parser.addoption("--host", default="127.0.0.1")
    parser.addoption("--port", default="5000")


@pytest.fixture
def host(request):
    """テスト対象ホスト"""
    return request.config.getoption("--host")


@pytest.fixture
def port(request):
    """テスト対象ポート"""
    return request.config.getoption("--port")


@pytest.fixture
def page(page):
    """Playwright ページ fixture"""
    from playwright.sync_api import expect

    timeout = 30000
    page.set_default_navigation_timeout(timeout)
    page.set_default_timeout(timeout)
    expect.set_options(timeout=timeout)

    return page


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """環境変数 RECORD_VIDEO=true でビデオ録画を有効化"""
    args = {**browser_context_args}

    if os.environ.get("RECORD_VIDEO", "").lower() == "true":
        video_dir = pathlib.Path("reports/videos")
        video_dir.mkdir(parents=True, exist_ok=True)
        args["record_video_dir"] = str(video_dir)
        args["record_video_size"] = {"width": 2400, "height": 1600}

    return args


# =============================================================================
# モックファクトリー fixture
# =============================================================================


@pytest.fixture
def mock_gpio_factory(mocker):
    """GPIO モックファクトリー"""
    from tests.fixtures import GPIOMockFactory

    factory = GPIOMockFactory()
    return lambda initial_states=None: factory.create(mocker, initial_states)


@pytest.fixture
def mock_fd_q10c_factory(mocker):
    """FD-Q10C モックファクトリー"""
    from tests.fixtures import FDQ10CMockFactory

    factory = FDQ10CMockFactory()
    return lambda **kwargs: factory.create(mocker, **kwargs)


@pytest.fixture
def mock_influxdb_factory(mocker):
    """InfluxDB モックファクトリー"""
    from tests.fixtures import InfluxDBMockFactory

    factory = InfluxDBMockFactory()
    return lambda **kwargs: factory.create(mocker, **kwargs)


@pytest.fixture
def mock_zmq_factory(mocker):
    """ZeroMQ モックファクトリー"""
    from tests.fixtures import ZeroMQMockFactory

    factory = ZeroMQMockFactory()
    return lambda **kwargs: factory.create(mocker, **kwargs)


# =============================================================================
# センサーデータ生成 fixture
# =============================================================================


@pytest.fixture
def sensor_data_factory():
    """センサーデータファクトリー"""
    from tests.fixtures import SensorDataFactory

    return SensorDataFactory


@pytest.fixture
def gen_sense_data():
    """センサーデータ生成関数"""
    from tests.fixtures.sensor_data import create_sense_data_dict

    return create_sense_data_dict


# =============================================================================
# アサーションヘルパー fixture
# =============================================================================


@pytest.fixture
def liveness_checker(config):
    """Liveness チェッカー"""
    from tests.helpers import LivenessChecker

    return LivenessChecker(config)


@pytest.fixture
def slack_checker():
    """Slack 通知チェッカー"""
    from tests.helpers import SlackChecker

    return SlackChecker()


@pytest.fixture
def work_log_checker():
    """作業ログチェッカー"""
    from tests.helpers import WorkLogChecker

    return WorkLogChecker()


@pytest.fixture
def valve_state_checker():
    """バルブ状態チェッカー"""
    from tests.helpers import ValveStateChecker

    return ValveStateChecker()


# =============================================================================
# 時間ヘルパー fixture
# =============================================================================


@pytest.fixture
def time_helper():
    """時間ヘルパー"""
    from tests.helpers import TimeHelper

    return TimeHelper()


@pytest.fixture
def speedup_helper():
    """時間加速ヘルパー"""
    from tests.helpers import SpeedupHelper

    return SpeedupHelper(speedup=100)
