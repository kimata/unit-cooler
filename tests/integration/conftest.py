#!/usr/bin/env python3
"""結合テスト用 conftest.py"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# src ディレクトリを Python パスに追加
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from tests.helpers.component_manager import ComponentManager, FullSystemManager  # noqa: E402
from tests.helpers.port_manager import PortManager  # noqa: E402


@pytest.fixture(scope="function")
def port_manager():
    """ポートマネージャー fixture

    各テスト関数ごとに新しいポートマネージャーを作成し、
    テスト終了時にポートを解放する。
    """
    pm = PortManager()
    yield pm
    pm.release_all()


@pytest.fixture
def server_port(port_manager: PortManager) -> int:
    """ZeroMQ サーバー用のポートを取得"""
    return port_manager.find_unused_port()


@pytest.fixture
def actuator_port(port_manager: PortManager) -> int:
    """Actuator 用のポートを取得"""
    return port_manager.find_unused_port()


@pytest.fixture
def log_port(port_manager: PortManager) -> int:
    """ログサーバー用のポートを取得"""
    return port_manager.find_unused_port()


@pytest.fixture
def http_port(port_manager: PortManager) -> int:
    """HTTP サーバー用のポートを取得"""
    return port_manager.find_unused_port()


@pytest.fixture(scope="function")
def component_manager():
    """コンポーネントマネージャー fixture

    テスト終了時に全コンポーネントを終了する。
    """
    cm = ComponentManager()
    yield cm
    cm.teardown_all()


@pytest.fixture(scope="function")
def full_system_manager():
    """フルシステムマネージャー fixture"""
    fsm = FullSystemManager()
    yield fsm
    fsm.teardown_all()


@pytest.fixture
def standard_mocks(mocker):
    """結合テスト用の標準モック

    GPIO、センサー、InfluxDB などの外部依存をモックする。
    """
    # GPIO モック
    mocker.patch("rpi_lgpio.open", return_value=0)
    mocker.patch("rpi_lgpio.close")
    mocker.patch("rpi_lgpio.gpio_claim_output")
    mocker.patch("rpi_lgpio.gpio_write")
    mocker.patch("rpi_lgpio.gpio_read", return_value=0)
    mocker.patch("rpi_lgpio.spi_open", return_value=0)
    mocker.patch("rpi_lgpio.spi_close")
    mocker.patch("rpi_lgpio.spi_xfer", return_value=(0, [0, 0, 0, 0, 0, 0, 0, 0]))

    # FD-Q10C センサーモック
    mocker.patch(
        "unit_cooler.actuator.sensor.fd_q10c_start",
        return_value={"worker_id": "test", "power": True},
    )
    mocker.patch("unit_cooler.actuator.sensor.fd_q10c_stop")
    mocker.patch("unit_cooler.actuator.sensor.fd_q10c_get_value", return_value=0.5)

    # InfluxDB モック
    mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100.0)
    mocker.patch("my_lib.sensor_data.get_last_data", return_value=30.0)

    return mocker
