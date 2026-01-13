"""
Test helper functions and fixtures for outdoor unit cooler tests.

This module contains common patterns extracted from test_basic.py to reduce code duplication.
"""

from __future__ import annotations

import copy
import fcntl
import logging
import os
import random
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


_port_lock = threading.Lock()
_used_ports = set()
_base_port = 10000  # Start from a higher port range to avoid system ports
_port_lock_file = Path(tempfile.gettempdir()) / "pytest_port_lock"


def _acquire_port_lock():
    """Acquire cross-process port allocation lock."""
    try:
        lock_fd = os.open(str(_port_lock_file), os.O_CREAT | os.O_WRONLY, 0o644)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return lock_fd
    except OSError:
        return None


def _release_port_lock(lock_fd):
    """Release cross-process port allocation lock."""
    if lock_fd is not None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except OSError:
            pass


def _load_used_ports():
    """Load used ports from shared file."""
    used_ports_file = Path(tempfile.gettempdir()) / "pytest_used_ports"
    try:
        with used_ports_file.open() as f:
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except (FileNotFoundError, ValueError):
        return set()


def _save_used_ports(used_ports):
    """Save used ports to shared file."""
    used_ports_file = Path(tempfile.gettempdir()) / "pytest_used_ports"
    try:
        with used_ports_file.open("w") as f:
            for port in sorted(used_ports):
                f.write(f"{port}\n")
    except OSError:
        pass


def _find_unused_port():
    """Find an unused port using cross-process coordination."""
    lock_fd = _acquire_port_lock()
    if lock_fd is None:
        # Fallback to simple system allocation if locking fails
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("localhost", 0))
            return sock.getsockname()[1]

    try:
        # Load currently used ports from all processes
        used_ports = _load_used_ports()

        # Use worker ID for initial port range preference
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
        worker_num = int(worker_id.replace("gw", "")) if worker_id.startswith("gw") else 0

        # Calculate worker-specific starting point
        max_workers = 50
        worker_slot = worker_num % max_workers
        port_range_size = 500
        port_range_start = _base_port + (worker_slot * port_range_size)
        port_range_end = min(port_range_start + port_range_size - 1, 65535)

        # Try to find an available port
        for _attempt in range(50):
            if _attempt < 20 and port_range_start <= port_range_end:
                # Try worker-specific range first
                port = random.randint(port_range_start, port_range_end)  # noqa: S311
            else:
                # Try broader range
                port = random.randint(_base_port, 65535)  # noqa: S311

            if port in used_ports:
                continue

            # Test if port is actually available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("localhost", port))
                    # Port is available - record it and return
                    used_ports.add(port)
                    _save_used_ports(used_ports)
                    return port
                except OSError:
                    # Port not available, try next
                    continue

        # If we get here, fall back to system allocation
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("localhost", 0))
            port = sock.getsockname()[1]
            used_ports.add(port)
            _save_used_ports(used_ports)
            return port

    finally:
        _release_port_lock(lock_fd)


def _release_port(port):
    """Release a port from the used ports set across all processes."""
    lock_fd = _acquire_port_lock()
    if lock_fd is None:
        return

    try:
        used_ports = _load_used_ports()
        used_ports.discard(port)
        _save_used_ports(used_ports)
    finally:
        _release_port_lock(lock_fd)


def wait_for_set_cooling_working(timeout: float = 30.0) -> None:
    """
    Wait for ValveController.set_cooling_working to be called.

    This function uses a mock to detect when set_cooling_working is called and
    waits up to the specified timeout for it to happen.

    Args:
        timeout: Maximum time to wait in seconds (default: 30.0)

    Raises:
        pytest.fail: If set_cooling_working is not called within the timeout

    """
    from unit_cooler.actuator.valve_controller import ValveController

    set_cooling_working_called = threading.Event()
    # 元のメソッドを保存
    original_set_cooling_working = ValveController.set_cooling_working

    def mock_set_cooling_working(self, *args, **kwargs):
        # イベントをセット
        set_cooling_working_called.set()
        logging.info("ValveController.set_cooling_working was called")
        # 元のメソッドを呼び出す
        return original_set_cooling_working(self, *args, **kwargs)

    # ValveController.set_cooling_working をモックして待つ
    with mock.patch.object(ValveController, "set_cooling_working", mock_set_cooling_working):
        # set_cooling_working が呼ばれるまで最大 timeout 秒待つ
        if not set_cooling_working_called.wait(timeout=timeout):
            pytest.fail(f"set_cooling_working was not called within {timeout} seconds")


class ComponentManager:
    """Manages component startup and teardown for tests."""

    def __init__(self):
        """Initialize ComponentManager with empty handles."""
        self.handles = {}
        self.auto_teardown = True

    def start_actuator(self, config: dict[str, Any], server_port: int, log_port: int, **kwargs) -> tuple:
        """Start actuator with standard configuration."""
        import actuator

        default_config = {
            "speedup": 100,
            "msg_count": 1,
            "pub_port": server_port,
            "log_port": log_port,
        }
        default_config.update(kwargs)
        self.handles["actuator"] = actuator.start(config, default_config)
        return self.handles["actuator"]

    def start_controller(self, config: dict[str, Any], server_port: int, real_port: int, **kwargs) -> tuple:
        """Start controller with standard configuration."""
        import controller

        default_config = {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 2,
            "server_port": server_port,
            "real_port": real_port,
        }
        default_config.update(kwargs)
        self.handles["controller"] = controller.start(config, default_config)
        return self.handles["controller"]

    def start_webui(self, config: dict[str, Any], server_port: int, log_port: int, **kwargs) -> tuple:
        """Start webui with standard configuration."""
        import webui

        default_config = {
            "msg_count": 1,
            "dummy_mode": True,
            "pub_port": server_port,
            "log_port": log_port,
        }
        default_config.update(kwargs)
        self.handles["webui"] = webui.start(config, default_config)
        return self.handles["webui"]

    def wait_and_term_controller(self):
        """Wait and terminate controller explicitly."""
        if "controller" in self.handles:
            import controller

            controller.wait_and_term(*self.handles["controller"])
            del self.handles["controller"]

    def wait_and_term_actuator(self):
        """Wait and terminate actuator explicitly."""
        if "actuator" in self.handles:
            import actuator

            actuator.wait_and_term(*self.handles["actuator"])
            del self.handles["actuator"]

    def wait_and_term_webui(self):
        """Wait and terminate webui explicitly."""
        if "webui" in self.handles:
            import webui

            webui.wait_and_term(*self.handles["webui"])
            del self.handles["webui"]

    def teardown_all(self):
        """Teardown all started components."""
        if not self.auto_teardown:
            return

        import actuator
        import controller
        import webui

        if "controller" in self.handles:
            controller.wait_and_term(*self.handles["controller"])
        if "actuator" in self.handles:
            actuator.wait_and_term(*self.handles["actuator"])
        if "webui" in self.handles:
            webui.wait_and_term(*self.handles["webui"])


@pytest.fixture
def component_manager():
    """Fixture providing component management functionality."""
    manager = ComponentManager()
    yield manager
    manager.teardown_all()


@pytest.fixture
def standard_actuator_mocks(mocker):
    """Provide standard mock setup for most actuator tests."""
    from tests.test_basic import gen_sense_data, mock_fd_q10c, mock_gpio

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})
    return mocker


@pytest.fixture
def standard_mocks(mocker):
    """Provide standard mock setup for most actuator tests."""
    from tests.test_basic import gen_sense_data, mock_fd_q10c, mock_gpio

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    # Reset dummy_cooling_mode state to ensure test isolation
    import unit_cooler.controller.engine

    unit_cooler.controller.engine.dummy_cooling_mode.prev_mode = 0

    return mocker


@pytest.fixture
def controller_mocks(mocker):
    """Provide standard mock setup for controller tests."""
    from tests.test_basic import gen_sense_data

    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    return mocker


@pytest.fixture
def webapp_client(config, server_port, log_port):
    """Create a webapp test client with standard configuration."""
    import webui

    app = webui.create_app(
        config, {"msg_count": 1, "dummy_mode": True, "pub_port": server_port, "log_port": log_port}
    )
    client = app.test_client()
    yield client
    client.delete()


def check_standard_liveness(
    config: dict[str, Any], expected_states: dict[tuple[str, ...], bool] | None = None
):
    """Check standard liveness states for all components."""
    from tests.test_basic import check_liveness

    defaults = {
        ("controller",): True,
        ("actuator", "subscribe"): True,
        ("actuator", "control"): True,
        ("actuator", "monitor"): True,
        ("webui", "subscribe"): False,
    }

    if expected_states:
        defaults.update(expected_states)

    for path, expected in defaults.items():
        check_liveness(config, list(path), expected)


def check_controller_only_liveness(config: dict[str, Any]):
    """Apply common pattern for controller-only tests."""
    check_standard_liveness(
        config,
        {
            ("actuator", "subscribe"): False,
            ("actuator", "control"): False,
            ("actuator", "monitor"): False,
        },
    )


def check_standard_post_test(config: dict[str, Any]):
    """Perform standard post-test checks (liveness + slack notification)."""
    from tests.test_basic import check_notify_slack

    check_standard_liveness(config)
    check_notify_slack(None)


def create_fetch_data_mock(field_mappings: dict[str, Any]) -> Callable:
    """Create a fetch_data mock with custom field mappings."""
    from tests.test_basic import gen_sense_data

    def fetch_data_mock(
        db_config,
        measure,
        hostname,
        field,
        start="-30h",
        stop="now()",
        every_min=1,
        window_min=3,
        create_empty=True,
        last=False,
    ):
        return field_mappings.get(field, gen_sense_data())

    return fetch_data_mock


def advance_time_sequence(time_machine, minutes: list[int], sleep_duration: float = 1):
    """Advance time through a sequence of minutes with sleep intervals."""
    from tests.test_basic import move_to

    for minute in minutes:
        if isinstance(minute, tuple):
            move_to(time_machine, minute[1], minute[0])  # (hour, minute)
        else:
            move_to(time_machine, minute)
        time.sleep(sleep_duration)


def wait_for_worker_process(worker_name: str = "control_worker", timeout: float = 1.0) -> bool:
    """ワーカーの処理完了を待機する

    Args:
        worker_name: 待機するワーカー名（"control_worker", "monitor_worker"）
        timeout: 最大待機時間（秒）

    Returns:
        処理完了通知を受け取った場合 True、タイムアウトした場合 False
    """
    import unit_cooler.actuator.worker

    return unit_cooler.actuator.worker.get_worker_state(worker_name).wait_for_process(timeout)


def wait_for_control_process(timeout: float = 1.0) -> bool:
    """control_worker の処理完了を待機する（便利関数）"""
    return wait_for_worker_process("control_worker", timeout)


def wait_for_monitor_process(timeout: float = 1.0) -> bool:
    """monitor_worker の処理完了を待機する（便利関数）"""
    return wait_for_worker_process("monitor_worker", timeout)


def wait_for_control_count(target_count: int, timeout: float = 1.0) -> bool:
    """control_worker が指定回数の処理を完了するまで待機する

    Args:
        target_count: 待機する処理回数
        timeout: 最大待機時間（秒）

    Returns:
        目標回数に達した場合 True、タイムアウトした場合 False
    """
    import unit_cooler.actuator.worker

    return unit_cooler.actuator.worker.get_worker_state("control_worker").wait_for_count(
        target_count, timeout
    )


def get_control_process_count() -> int:
    """control_worker の現在の処理回数を取得する"""
    import unit_cooler.actuator.worker

    return unit_cooler.actuator.worker.get_worker_state("control_worker").get_count()


# =============================================================================
# StateManager ベースの待機関数
# =============================================================================
def get_state_manager():
    """StateManager インスタンスを取得"""
    from unit_cooler.state_manager import get_state_manager as _get_state_manager

    return _get_state_manager()


def reset_state_manager():
    """StateManager をリセット"""
    from unit_cooler.state_manager import reset_state_manager as _reset_state_manager

    _reset_state_manager()


def wait_for_valve_open(timeout: float = 5.0) -> bool:
    """バルブが OPEN になるまで待機"""
    return get_state_manager().wait_for_valve_open(timeout)


def wait_for_valve_close(timeout: float = 5.0) -> bool:
    """バルブが CLOSE になるまで待機"""
    return get_state_manager().wait_for_valve_close(timeout)


def wait_for_cooling_working(timeout: float = 5.0) -> bool:
    """冷却が WORKING になるまで待機"""
    return get_state_manager().wait_for_cooling_working(timeout)


def wait_for_cooling_idle(timeout: float = 5.0) -> bool:
    """冷却が IDLE になるまで待機"""
    return get_state_manager().wait_for_cooling_idle(timeout)


def wait_for_state(predicate, timeout: float = 5.0) -> bool:
    """カスタム条件で待機

    Args:
        predicate: StateManager を受け取り bool を返す関数
        timeout: 最大待機時間（秒）

    Example:
        wait_for_state(lambda s: s.control_worker_count >= 5)
    """
    return get_state_manager().wait_for(predicate, timeout)


def sm_wait_for_control_count(target_count: int, timeout: float = 5.0) -> bool:
    """StateManager 経由で control_worker の処理回数を待機"""
    return get_state_manager().wait_for_control_count(target_count, timeout)


def sm_wait_for_monitor_count(target_count: int, timeout: float = 5.0) -> bool:
    """StateManager 経由で monitor_worker の処理回数を待機"""
    return get_state_manager().wait_for_monitor_count(target_count, timeout)


def sm_wait_for_subscribe_count(target_count: int, timeout: float = 5.0) -> bool:
    """StateManager 経由で subscribe_worker の処理回数を待機"""
    return get_state_manager().wait_for_count("subscribe_worker_count", target_count, timeout)


def sm_wait_for_control_process(timeout: float = 1.0) -> bool:
    """StateManager 経由で control_worker の次の処理を待機"""
    return get_state_manager().wait_for_control_process(timeout)


def sm_wait_for_monitor_process(timeout: float = 1.0) -> bool:
    """StateManager 経由で monitor_worker の次の処理を待機"""
    return get_state_manager().wait_for_monitor_process(timeout)


def advance_time_with_sync(
    time_machine, minute: int | tuple[int, int], worker_name: str = "control_worker", timeout: float = 1.0
):
    """時間を進めてワーカーの処理完了を待機する

    time.sleep() + move_to() のパターンを置き換える。
    ワーカーが実際に処理を完了するまで待機するため、
    テストの信頼性が向上し、不要な待ち時間を削減できる。

    Args:
        time_machine: time_machine fixture
        minute: 進める時刻（分、または (時, 分) のタプル）
        worker_name: 待機するワーカー名
        timeout: 最大待機時間（秒）

    Returns:
        ワーカーが処理を完了した場合 True
    """
    from tests.test_basic import move_to

    if isinstance(minute, tuple):
        move_to(time_machine, minute[1], minute[0])  # (hour, minute)
    else:
        move_to(time_machine, minute)

    return wait_for_worker_process(worker_name, timeout)


def advance_time_sequence_with_sync(
    time_machine,
    minutes: list[int | tuple[int, int]],
    worker_name: str = "control_worker",
    timeout: float = 1.0,
):
    """時間を順次進めてワーカーの処理完了を待機する

    advance_time_sequence() の改良版。time.sleep() の代わりに
    ワーカーの処理完了イベントを使用して同期する。

    Args:
        time_machine: time_machine fixture
        minutes: 進める時刻のリスト
        worker_name: 待機するワーカー名
        timeout: 各ステップの最大待機時間（秒）
    """
    for minute in minutes:
        advance_time_with_sync(time_machine, minute, worker_name, timeout)


def control_message_modifier(mocker):
    """Modify control message list settings. Takes mocker as parameter."""

    def modify_duty_settings(**kwargs):
        import unit_cooler.controller.message
        from unit_cooler.controller.message import CONTROL_MESSAGE_LIST as CONTROL_MESSAGE_LIST_ORIG

        message_list = copy.deepcopy(CONTROL_MESSAGE_LIST_ORIG)
        for key, value in kwargs.items():
            if "." in key:
                # Support nested keys like "duty.on_sec"
                keys = key.split(".")
                target = message_list[-1]
                for k in keys[:-1]:
                    target = target[k]
                target[keys[-1]] = value
            else:
                message_list[-1]["duty"][key] = value

        mocker.patch.object(unit_cooler.controller.message, "CONTROL_MESSAGE_LIST", message_list)
        return message_list

    return modify_duty_settings


@pytest.fixture
def control_message_modifier_fixture(mocker):
    """Fixture version of control_message_modifier for tests that need it as a fixture."""
    return control_message_modifier(mocker)


def assert_standard_api_response(response, required_fields: list[str] | None = None):
    """Assert standard API response structure."""
    if response.status_code != 200:
        msg = f"Expected status 200, got {response.status_code}"
        raise AssertionError(msg)
    json_data = response.json

    default_fields = ["watering", "sensor", "mode", "cooler_status", "outdoor_status"]
    fields_to_check = required_fields or default_fields

    for field in fields_to_check:
        if field not in json_data:
            msg = f"Required field '{field}' not found in response"
            raise AssertionError(msg)


def run_standard_test_sequence(component_manager, test_func, config, server_port, real_port, **kwargs):
    """Run a standard test sequence with component startup, test execution, and teardown."""
    # Start components
    log_port = kwargs.get("log_port", 5001)
    actuator_kwargs = kwargs.get("actuator_kwargs", {})
    controller_kwargs = kwargs.get("controller_kwargs", {})

    component_manager.start_actuator(config, server_port, log_port, **actuator_kwargs)
    component_manager.start_controller(config, server_port, real_port, **controller_kwargs)

    # Run the test function
    test_func(config, server_port, real_port, log_port)

    # Components will be torn down automatically by the fixture


# Pre-configured field mappings for common test scenarios
OUTDOOR_NORMAL_FIELDS = {
    "temp": None,  # Will use gen_sense_data([25]) in actual usage
    "power": None,  # Will use gen_sense_data([100]) in actual usage
    "lux": None,  # Will use gen_sense_data([500]) in actual usage
    "solar_rad": None,  # Will use gen_sense_data([300]) in actual usage
}

TEMP_LOW_FIELDS = {
    "temp": None,  # Will use gen_sense_data([15]) in actual usage
    "power": None,  # Will use gen_sense_data([100]) in actual usage
}

POWER_OFF_FIELDS = {
    "temp": None,  # Will use gen_sense_data([35]) in actual usage
    "power": None,  # Will use gen_sense_data([0]) in actual usage
}


def mock_react_index_html(mocker):
    """
    Mock flask.send_from_directory to handle react/dist/index.html fallback.

    Returns actual file if it exists, otherwise returns dummy HTML containing "室外機".
    This allows tests to pass even when React build hasn't been completed.
    """
    from flask import Response

    def mock_send_from_directory(directory, filename, **kwargs):
        if filename == "index.html":
            import pathlib

            file_path = pathlib.Path(directory) / filename
            if file_path.exists():
                # ファイルが存在する場合は実際のファイルを返す
                import flask

                return flask.helpers.send_from_directory(directory, filename, **kwargs)
            else:
                # ファイルが存在しない場合はダミーHTMLを返す
                logging.debug("index.html not found at %s, returning dummy HTML for testing", file_path)
                dummy_html = """<!DOCTYPE html>
<html>
<head><title>室外機自動冷却システム</title></head>
<body><h1>室外機</h1></body>
</html>"""
                return Response(dummy_html, mimetype="text/html")
        # 他のファイルは元の関数を使用して処理
        import flask

        return flask.helpers.send_from_directory(directory, filename, **kwargs)

    mocker.patch("flask.send_from_directory", side_effect=mock_send_from_directory)


def create_config_with_giveup(config, giveup: int):
    """
    Create a modified Config with a custom giveup value.

    Since Config is a frozen dataclass, we need to use dataclasses.replace
    at each level to modify nested values.
    """
    import dataclasses

    # Create new SenseConfig with custom giveup
    new_sense = dataclasses.replace(config.actuator.monitor.sense, giveup=giveup)

    # Create new MonitorConfig with new SenseConfig
    new_monitor = dataclasses.replace(config.actuator.monitor, sense=new_sense)

    # Create new ActuatorConfig with new MonitorConfig
    new_actuator = dataclasses.replace(config.actuator, monitor=new_monitor)

    # Create new Config with new ActuatorConfig
    return dataclasses.replace(config, actuator=new_actuator)
