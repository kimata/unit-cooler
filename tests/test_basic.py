#!/usr/bin/env python3
# ruff: noqa: S101

import datetime
import json
import logging
import os
import pathlib
import sys
import time
import unittest

import my_lib.notify.slack
import my_lib.webapp.config
import pytest

from tests.test_helpers import (
    _find_unused_port,
    _release_port,
    check_controller_only_liveness,
    check_standard_liveness,
    check_standard_post_test,
    control_message_modifier,
    create_fetch_data_mock,
    mock_react_index_html,
    wait_for_set_cooling_working,
)

my_lib.webapp.config.URL_PREFIX = "/unit-cooler"

CONFIG_FILE = "config.example.yaml"
SCHEMA_CONFIG = "config.schema"


@pytest.fixture(scope="session", autouse=True)
def env_mock():
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
    with unittest.mock.patch(
        "my_lib.notify.slack.slack_sdk.web.client.WebClient.chat_postMessage",
        return_value={"ok": True, "ts": "1234567890.123456"},
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session")
def config():
    import my_lib.config

    return my_lib.config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))


@pytest.fixture
def server_port():
    port = _find_unused_port()
    yield port
    _release_port(port)


@pytest.fixture
def real_port():
    port = _find_unused_port()
    yield port
    _release_port(port)


@pytest.fixture
def log_port():
    port = _find_unused_port()
    yield port
    _release_port(port)


@pytest.fixture(autouse=True)
def _clear(config):
    import my_lib.config
    import my_lib.footprint
    import my_lib.webapp.log

    with unittest.mock.patch.dict("os.environ", {"DUMMY_MODE": "true"}):
        import unit_cooler.actuator.control
        import unit_cooler.actuator.valve
        import unit_cooler.actuator.work_log

    liveness_conf_path_list = [
        ["controller"],
        ["actuator", "subscribe"],
        ["actuator", "control"],
        ["actuator", "monitor"],
        ["webui", "subscribe"],
    ]

    for conf_path in liveness_conf_path_list:
        my_lib.footprint.clear(my_lib.config.get_path(config, conf_path, ["liveness", "file"]))

    unit_cooler.actuator.control.hazard_clear(config)
    unit_cooler.actuator.valve.clear_stat()
    unit_cooler.actuator.work_log.hist_clear()

    my_lib.webapp.log.term()

    my_lib.notify.slack.interval_clear()
    my_lib.notify.slack.hist_clear()

    if "my_lib.sensor.fd_q10c" in sys.modules:
        logging.debug("unload my_lib.sensor.fd_q10c")
        del sys.modules["my_lib.sensor.fd_q10c"]


@pytest.fixture(autouse=True)
def fluent_mock():
    with unittest.mock.patch("fluent.sender.FluentSender.emit") as fixture:

        def emit_mock(label, data):  # noqa: ARG001
            return True

        fixture.side_effect = emit_mock

        yield fixture


def move_to(time_machine, minute, hour=0):
    import my_lib.time

    logging.info("TIME move to %02d:%02d", hour, minute)
    time_machine.move_to(my_lib.time.now().replace(hour=hour, minute=minute, second=0))


def gen_sense_data(value=[30, 34, 25], valid=True):  # noqa: B006
    sensor_data = {
        "value": value,
        "time": [],
        "valid": valid,
    }

    for i in range(len(value)):
        sensor_data["time"].append(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=i - len(value))
        )

    return sensor_data


def gen_fd_q10c_ser_trans_sense(is_zero=False):
    # NOTE: send/recv はプログラム視点。SPI デバイスが送信すべき内容が recv。
    if is_zero:
        return [
            {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
            {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
            {"send": [0x62, 0x12, 0x07], "recv": [0x62, 0x12, 0x07, 0x2D]},
            {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD4, 0x1B]},
            {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x00, 0x2D]},
            {"send": [0xE2, 0x18], "recv": [0xE2, 0x18, 0x00, 0x2D]},
            {"send": [0xE3, 0x09], "recv": [0xE3, 0x09, 0xD4, 0x1B]},
        ]
    else:
        return [
            {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
            {"send": [0x61, 0x2E, 0x94], "recv": [0x61, 0x2E, 0x94, 0x2D]},
            {"send": [0x62, 0x12, 0x7], "recv": [0x62, 0x12, 0x7, 0x2D]},
            {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD4, 0x1B]},
            {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x1, 0x3C]},
            {"send": [0xE2, 0x18], "recv": [0xE2, 0x18, 0x1, 0x3C]},
            {"send": [0xE3, 0x9], "recv": [0xE3, 0x9, 0xD4, 0x1B]},
        ]


def gen_fd_q10c_ser_trans_ping():
    # NOTE: send/recv はプログラム視点。SPI デバイスが送信すべき内容が recv。
    return [
        {"send": [0x70, 0x09, 0x93], "recv": [0x70, 0x09, 0x93, 0x2D]},
        {"send": [0x61, 0x35, 0x12], "recv": [0x61, 0x35, 0x12, 0x2D]},
        {"send": [0x62, 0x09, 0x81], "recv": [0x62, 0x09, 0x81, 0x2D]},
        {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD9, 0x3A]},
        {"send": [0xE1, 0x28], "recv": [0xE1, 0x28, 0x46, 0x06]},
        {"send": [0xE2, 0x18], "recv": [0xE2, 0x18, 0x44, 0x27]},
        {"send": [0xE3, 0x09], "recv": [0xE3, 0x09, 0x2D, 0x28]},
        {"send": [0xE4, 0x2B], "recv": [0xE4, 0x2B, 0x51, 0x30]},
        {"send": [0xE5, 0x3A], "recv": [0xE5, 0x3A, 0x31, 0x0C]},
        {"send": [0xE6, 0x0A], "recv": [0xE6, 0x0A, 0x30, 0x1D]},
        {"send": [0xE7, 0x1B], "recv": [0xE7, 0x1B, 0x43, 0x05]},
        {"send": [0xE8, 0x1B], "recv": [0xE8, 0x1B, 0xE5, 0x3A]},
    ]


def check_liveness(config, conf_path, is_healthy, threshold_sec=120):
    import my_lib.config
    import my_lib.footprint

    name = " - ".join(conf_path)
    liveness_file = my_lib.config.get_path(config, conf_path, ["liveness", "file"])

    assert (my_lib.footprint.elapsed(liveness_file) < threshold_sec) == is_healthy, (
        f"{name} の healthz が更新されていま{'せん' if is_healthy else 'す'}。"
    )


def check_notify_slack(message, index=-1):
    import my_lib.notify.slack

    notify_hist = my_lib.notify.slack.hist_get(False)
    logging.debug(notify_hist)

    if message is None:
        assert notify_hist == [], "正常なはずなのに、エラー通知がされています。"
    else:
        assert len(notify_hist) != 0, "異常が発生したはずなのに、エラー通知がされていません。"
        assert notify_hist[index].find(message) != -1, f"「{message}」が Slack で通知されていません。"


def check_work_log(message):
    import unit_cooler.actuator.work_log

    if message is None:
        assert unit_cooler.actuator.work_log.hist_get() == [], "正常なはずなのに、エラー通知がされています。"
    else:
        work_log_hist = unit_cooler.actuator.work_log.hist_get()
        assert len(work_log_hist) != 0, "異常が発生したはずなのに、エラー通知がされていません。"
        # 履歴全体から該当メッセージを探す（最後のメッセージだけでなく）
        found = any(msg.find(message) != -1 for msg in work_log_hist)
        assert found, f"「{message}」が work_log で通知されていません。"


def mock_fd_q10c(mocker, ser_trans=gen_fd_q10c_ser_trans_sense(), count=0, spi_read=0x11):  # noqa: B008
    import struct

    from my_lib.sensor.fd_q10c import FD_Q10C

    spidev_mock = mocker.MagicMock()
    spidev_mock.xfer2.return_value = [0x00, spi_read]
    mocker.patch("spidev.SpiDev", return_value=spidev_mock)

    def ser_read_mock(length):  # noqa: ARG001
        ser_read_mock.i += 1

        if ser_read_mock.i == count:
            raise RuntimeError
        for trans in ser_trans:
            if trans["send"] == ser_read_mock.write_data:
                return struct.pack("B" * len(trans["recv"]), *trans["recv"])

        logging.warning("Unknown serial transfer")
        return None

    ser_read_mock.i = 0

    ser_read_mock.write_data = None

    def ser_write_mock(data):
        ser_read_mock.write_data = list(struct.unpack("B" * len(data), data))

    ser_mock = mocker.MagicMock()
    ser_mock.read.side_effect = ser_read_mock
    ser_mock.write.side_effect = ser_write_mock
    mocker.patch("serial.Serial", return_value=ser_mock)

    mocker.patch("unit_cooler.actuator.sensor.FD_Q10C", new=FD_Q10C)


def mock_gpio(mocker):
    gpio_mock = mocker.MagicMock()

    def gpio_output_mock(gpio, value):
        gpio_input_mock.data[gpio] = value

    def gpio_input_mock(gpio):
        return gpio_input_mock.data[gpio]

    gpio_input_mock.data = [0 for i in range(32)]

    gpio_mock.output.side_effect = gpio_output_mock
    gpio_mock.input.side_effect = gpio_input_mock

    mocker.patch("my_lib.rpi.gpio", new=gpio_mock)


######################################################################
@pytest.mark.order(6)
def test_controller(config, server_port, real_port):
    import controller

    # Start and immediately wait for controller completion
    controller.wait_and_term(
        *controller.start(
            config,
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
                "disable_proxy": True,
            },
        )
    )

    # Check liveness - controller should be up, others down
    check_controller_only_liveness(config)
    check_notify_slack(None)


def test_controller_influxdb_dummy(mocker, config, server_port, real_port):
    import controller

    # Setup InfluxDB mock with dummy data
    def value_mock():
        value_mock.i += 1
        return None if value_mock.i == 1 else 1

    value_mock.i = 0

    table_entry_mock = mocker.MagicMock()
    record_mock = mocker.MagicMock()
    query_api_mock = mocker.MagicMock()
    mocker.patch.object(record_mock, "get_value", side_effect=value_mock)
    mocker.patch.object(record_mock, "get_time", return_value=datetime.datetime.now(datetime.timezone.utc))
    table_entry_mock.__iter__.return_value = [record_mock, record_mock]
    type(table_entry_mock).records = table_entry_mock
    query_api_mock.query.return_value = [table_entry_mock]
    mocker.patch("influxdb_client.InfluxDBClient.query_api", return_value=query_api_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "speedup": 100,
                "dummy_mode": True,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
                "disable_proxy": True,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack(None)


def test_controller_start_error_1(controller_mocks, config, server_port, real_port):
    from threading import Thread as Thread_orig

    import controller

    def thread_mock(group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None):  # noqa: ARG001, B006, PLR0913
        thread_mock.i += 1
        if thread_mock.i == 1:
            raise RuntimeError
        return Thread_orig(target=target, args=args)

    thread_mock.i = 0

    controller_mocks.patch("threading.Thread", new=thread_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_standard_liveness(
        config,
        {
            ("controller",): False,
            ("actuator", "subscribe"): False,
            ("actuator", "control"): False,
            ("actuator", "monitor"): False,
        },
    )
    check_notify_slack("Traceback")


def test_controller_start_error_2(controller_mocks, config, server_port, real_port):
    from threading import Thread as Thread_orig

    import controller

    def thread_mock(group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None):  # noqa: ARG001, B006, PLR0913
        thread_mock.i += 1
        if thread_mock.i == 1:
            raise RuntimeError
        return Thread_orig(target=target, args=args)

    thread_mock.i = 0

    controller_mocks.patch("threading.Thread", new=thread_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": False,  # NOTE: Proxy をエラーにするテストなので動かして OK
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_standard_liveness(
        config,
        {
            ("controller",): False,
            ("actuator", "subscribe"): False,
            ("actuator", "control"): False,
            ("actuator", "monitor"): False,
        },
    )
    check_notify_slack("Traceback")


def test_controller_influxdb_error(mocker, config, server_port, real_port):
    import controller

    mocker.patch("influxdb_client.InfluxDBClient.query_api", side_effect=RuntimeError())

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack("エアコン動作モードを判断できません。")


def test_controller_outdoor_normal(mocker, config, server_port, real_port):
    import controller

    fetch_data_mock = create_fetch_data_mock(
        {
            "temp": gen_sense_data([25]),
            "power": gen_sense_data([100]),
            "lux": gen_sense_data([500]),
            "solar_rad": gen_sense_data([300]),
        }
    )

    mocker.patch("my_lib.sensor_data.fetch_data", side_effect=fetch_data_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,  # NOTE: subscriber がいないので、proxy を無効化
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack(None)


def test_controller_aircon_mode(mocker, config, server_port, real_port):
    import controller

    def fetch_data_mock(  # noqa: PLR0913, PLR0911
        db_config,  # noqa: ARG001
        measure,  # noqa: ARG001
        hostname,  # noqa: ARG001
        field,
        start="-30h",  # noqa: ARG001
        stop="now()",  # noqa: ARG001
        every_min=1,  # noqa: ARG001
        window_min=3,  # noqa: ARG001
        create_empty=True,  # noqa: ARG001
        last=False,  # noqa: ARG001
    ):
        if field == "temp":
            return gen_sense_data([30])
        elif field == "power":
            fetch_data_mock.i += 1
            if (fetch_data_mock.i % 5) == 0:
                return gen_sense_data([0])
            elif (fetch_data_mock.i % 5) == 1:
                return gen_sense_data([10])
            elif (fetch_data_mock.i % 5) == 2:
                return gen_sense_data([50])
            elif (fetch_data_mock.i % 5) == 3:
                return gen_sense_data([600])
            else:
                return gen_sense_data([1100])
        else:
            return gen_sense_data([30])

    fetch_data_mock.i = 0

    mocker.patch("my_lib.sensor_data.fetch_data", side_effect=fetch_data_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,  # NOTE: subscriber がいないので、proxy を無効化
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack(None)


def test_controller_aircon_invalid(mocker, config, server_port, real_port):
    import controller

    def fetch_data_mock(  # noqa: PLR0913
        db_config,  # noqa: ARG001
        measure,  # noqa: ARG001
        hostname,  # noqa: ARG001
        field,
        start="-30h",  # noqa: ARG001
        stop="now()",  # noqa: ARG001
        every_min=1,  # noqa: ARG001
        window_min=3,  # noqa: ARG001
        create_empty=True,  # noqa: ARG001
        last=False,  # noqa: ARG001
    ):
        if field == "power":
            sensor_data = gen_sense_data()
            sensor_data["valid"] = False
            return sensor_data
        else:
            return gen_sense_data()

    mocker.patch("my_lib.sensor_data.fetch_data", side_effect=fetch_data_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,  # NOTE: subscriber がいないので、proxy を無効化
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], False)
    check_liveness(config, ["actuator", "control"], False)
    check_liveness(config, ["actuator", "monitor"], False)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("データを取得できませんでした。")


def test_controller_temp_invalid(mocker, config, server_port, real_port):
    import controller

    def fetch_data_mock(  # noqa: PLR0913
        db_config,  # noqa: ARG001
        measure,  # noqa: ARG001
        hostname,  # noqa: ARG001
        field,
        start="-30h",  # noqa: ARG001
        stop="now()",  # noqa: ARG001
        every_min=1,  # noqa: ARG001
        window_min=3,  # noqa: ARG001
        create_empty=True,  # noqa: ARG001
        last=False,  # noqa: ARG001
    ):
        if field == "temp":
            sensor_data = gen_sense_data()
            sensor_data["valid"] = False
            return sensor_data
        else:
            return gen_sense_data()

    mocker.patch("my_lib.sensor_data.fetch_data", side_effect=fetch_data_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,  # NOTE: subscriber がいないので、proxy を無効化
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack("エアコン動作モードを判断できません。")


def test_controller_temp_low(mocker, config, server_port, real_port):
    import controller

    def fetch_data_mock(  # noqa: PLR0913
        db_config,  # noqa: ARG001
        measure,  # noqa: ARG001
        hostname,  # noqa: ARG001
        field,
        start="-30h",  # noqa: ARG001
        stop="now()",  # noqa: ARG001
        every_min=1,  # noqa: ARG001
        window_min=3,  # noqa: ARG001
        create_empty=True,  # noqa: ARG001
        last=False,  # noqa: ARG001
    ):
        if field == "temp":
            return gen_sense_data([0])
        else:
            return gen_sense_data()

    mocker.patch("my_lib.sensor_data.fetch_data", side_effect=fetch_data_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,  # NOTE: subscriber がいないので、proxy を無効化
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack(None)


def test_controller_sensor_error(mocker, config, server_port, real_port):
    import controller

    mocker.patch("influxdb_client.InfluxDBClient.query_api", side_effect=RuntimeError())

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,  # NOTE: subscriber がいないので、proxy を無効化
                "speedup": 100,
                "msg_count": 1,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack("エアコン動作モードを判断できません。")


def test_controller_dummy_error(controller_mocks, config, server_port, real_port):
    import controller

    def send_string_mock(*args, **kwargs):  # noqa: ARG001
        send_string_mock.i += 1
        if send_string_mock.i == 1:
            return True
        else:
            raise RuntimeError

    send_string_mock.i = 0

    controller_mocks.patch("unit_cooler.pubsub.publish.zmq.Socket.send_string", side_effect=send_string_mock)

    controller.wait_and_term(
        *controller.start(
            config,
            {
                "disable_proxy": True,
                "speedup": 100,
                "msg_count": 1,
                "dummy_mode": True,
                "server_port": server_port,
                "real_port": real_port,
            },
        )
    )

    check_controller_only_liveness(config)
    check_notify_slack(None)


@pytest.mark.order(5)
def test_actuator(component_manager, config, server_port, real_port, log_port):
    # Start actuator and controller in sequence
    component_manager.start_actuator(config, server_port, log_port, msg_count=1)
    component_manager.start_controller(config, server_port, real_port, msg_count=1)

    # Wait for completion
    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_post_test(config)


@pytest.mark.order(4)
def test_actuator_normal(  # noqa: PLR0913
    standard_mocks, component_manager, config, server_port, real_port, log_port
):
    import unit_cooler.controller.message

    # Mock cooling mode for normal operation
    standard_mocks.patch(
        "unit_cooler.controller.engine.dummy_cooling_mode",
        return_value={"cooling_mode": len(unit_cooler.controller.message.CONTROL_MESSAGE_LIST) - 1},
    )

    # Start both components with reduced speedup for normal operation
    component_manager.start_actuator(config, server_port, log_port, speedup=100, msg_count=5)
    component_manager.start_controller(config, server_port, real_port, speedup=100, msg_count=5)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_post_test(config)


def test_actuator_duty_disable(  # noqa: PLR0913
    standard_mocks, component_manager, config, server_port, real_port, log_port
):
    from unit_cooler.controller.message import CONTROL_MESSAGE_LIST as CONTROL_MESSAGE_LIST_ORIG

    standard_mocks.patch(
        "unit_cooler.controller.engine.dummy_cooling_mode",
        return_value={"cooling_mode": len(CONTROL_MESSAGE_LIST_ORIG) - 1},
    )

    # Use the helper to modify duty settings
    control_message_modifier(standard_mocks)(enable=False)

    component_manager.start_actuator(config, server_port, log_port, msg_count=5)
    component_manager.start_controller(config, server_port, real_port, msg_count=5)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_post_test(config)


@pytest.mark.order(7)
def test_actuator_log(  # noqa: PLR0913, PLR0915
    standard_mocks,  # noqa: ARG001
    component_manager,
    config,
    server_port,
    real_port,
    log_port,
):
    import requests

    component_manager.start_actuator(config, server_port, log_port, msg_count=20)
    component_manager.start_controller(config, server_port, real_port, msg_count=20)

    requests.Session().mount(
        "http://",
        requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=120,
                connect=100,
                backoff_factor=10,
            )
        ),
    )

    # NOTE: set_cooling_working が呼ばれるまで最大30秒待つ
    wait_for_set_cooling_working()

    time.sleep(2)

    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        timeout=15,
    )
    assert res.status_code == 200
    assert "data" in json.loads(res.text)
    assert len(json.loads(res.text)["data"]) != 0
    assert (
        datetime.datetime.strptime(json.loads(res.text)["data"][0]["date"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=my_lib.time.get_zoneinfo()
        )
        - my_lib.time.now()
    ).total_seconds() < 5
    assert (
        datetime.datetime.fromtimestamp(json.loads(res.text)["last_time"], tz=my_lib.time.get_zoneinfo())
        - my_lib.time.now()
    ).total_seconds() < 5

    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/log_clear",
        timeout=15,
    )
    assert res.status_code == 200
    assert json.loads(res.text)["result"] == "success"

    time.sleep(2)

    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/log_view",
        timeout=15,
    )
    assert res.status_code == 200
    assert "data" in json.loads(res.text)
    assert json.loads(res.text)["data"][-1]["message"].find("ログがクリアされました。") != -1
    assert (
        datetime.datetime.strptime(json.loads(res.text)["data"][-1]["date"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=my_lib.time.get_zoneinfo()
        )
        - my_lib.time.now()
    ).total_seconds() < 5
    assert (
        datetime.datetime.fromtimestamp(json.loads(res.text)["last_time"], tz=my_lib.time.get_zoneinfo())
        - my_lib.time.now()
    ).total_seconds() < 5

    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/log_view",
        headers={"Accept-Encoding": "gzip"},
        params={
            "callback": "TEST",
        },
        timeout=15,
    )
    assert res.status_code == 200
    assert res.text.find("TEST(") == 0

    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/event",
        params={"count": "1"},
        timeout=15,
    )
    assert res.status_code == 200
    assert res.text.strip() == "data: log"

    # Test valve_status endpoint
    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/valve_status",
        timeout=15,
    )
    assert res.status_code == 200
    valve_status = json.loads(res.text)
    assert "state" in valve_status
    assert "state_value" in valve_status
    assert "duration" in valve_status
    assert valve_status["state"] in ["OPEN", "CLOSE"]
    assert valve_status["state_value"] in [0, 1]
    assert isinstance(valve_status["duration"], (int, float))
    assert valve_status["duration"] >= 0

    # Test valve_status endpoint with JSONP callback
    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/valve_status",
        params={"callback": "valveCallback"},
        timeout=15,
    )
    assert res.status_code == 200
    assert res.text.startswith("valveCallback(")

    # Test get_flow endpoint
    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/get_flow",
        timeout=15,
    )
    assert res.status_code == 200
    flow_status = json.loads(res.text)
    assert "flow" in flow_status
    assert isinstance(flow_status["flow"], (int, float))
    assert flow_status["flow"] >= 0

    # Test get_flow endpoint with JSONP callback
    res = requests.get(
        f"http://localhost:{log_port}/{my_lib.webapp.config.URL_PREFIX}/api/get_flow",
        params={"callback": "flowCallback"},
        timeout=15,
    )
    assert res.status_code == 200
    assert res.text.startswith("flowCallback(")
    assert res.text.endswith(")")

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_post_test(config)


def test_actuator_send_error(  # noqa: PLR0913
    standard_mocks, component_manager, config, server_port, real_port, log_port
):
    standard_mocks.patch("fluent.sender.FluentSender", new=RuntimeError())

    component_manager.start_actuator(config, server_port, log_port)
    component_manager.start_controller(config, server_port, real_port)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(
        config,
        {
            ("actuator", "monitor"): False,
        },
    )
    check_notify_slack("流量のロギングを開始できません。")


def test_actuator_mode_const(  # noqa: PLR0913
    standard_mocks, component_manager, config, server_port, real_port, log_port
):
    standard_mocks.patch("unit_cooler.controller.engine.dummy_cooling_mode", return_value={"cooling_mode": 1})

    component_manager.start_actuator(config, server_port, log_port)
    component_manager.start_controller(config, server_port, real_port)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(config)
    check_notify_slack(None)


@pytest.mark.order(10)
def test_actuator_power_off_1(  # noqa: PLR0913
    standard_mocks, component_manager, time_machine, config, server_port, real_port, log_port
):
    standard_mocks.patch("unit_cooler.actuator.sensor.get_flow", return_value=0)

    # 現実的なモック：stop()が呼ばれた後はget_power_state()がFalseを返すようにする
    power_state = {"is_on": True}

    def mock_get_power_state():
        return power_state["is_on"]

    def mock_stop():
        power_state["is_on"] = False

    standard_mocks.patch("unit_cooler.actuator.sensor.get_power_state", side_effect=mock_get_power_state)
    standard_mocks.patch("unit_cooler.actuator.sensor.stop", side_effect=mock_stop)

    def dummy_mode_mock():
        dummy_mode_mock.i += 1
        if dummy_mode_mock.i <= 1:
            return {"cooling_mode": 1}
        else:
            return {"cooling_mode": 0}

    dummy_mode_mock.i = 0

    standard_mocks.patch("unit_cooler.controller.engine.dummy_cooling_mode", side_effect=dummy_mode_mock)

    move_to(time_machine, 0)

    component_manager.start_actuator(config, server_port, log_port, msg_count=20)
    component_manager.start_controller(config, server_port, real_port, msg_count=20)

    time.sleep(0.3)  # Reduced from 1 for testing
    move_to(time_machine, 1)

    time.sleep(0.3)  # Reduced from 1 for testing
    move_to(time_machine, 2)

    time.sleep(0.5)  # Reduced from 2 for testing
    move_to(time_machine, 3, 1)

    time.sleep(0.5)  # Reduced from 2 for testing
    move_to(time_machine, 3, 2)

    time.sleep(0.5)  # Reduced from 2 for testing
    move_to(time_machine, 3, 3)

    time.sleep(0.5)  # Reduced from 2 for testing
    move_to(time_machine, 3, 4)

    time.sleep(0.5)  # Reduced from 2 for testing
    move_to(time_machine, 3, 5)

    time.sleep(0.5)  # Reduced from 2 for testing

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True, 10000)
    check_liveness(config, ["webui", "subscribe"], False)
    # NOTE: タイミング次第でエラーが記録されるので notify_slack はチェックしない
    check_work_log("長い間バルブが閉じられていますので、流量計の電源を OFF します。")


def test_actuator_power_off_2(  # noqa: PLR0913
    mocker, component_manager, time_machine, config, server_port, real_port, log_port
):
    mock_gpio(mocker)
    mock_fd_q10c(mocker, gen_fd_q10c_ser_trans_sense(True))
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    def dummy_mode_mock():
        dummy_mode_mock.i += 1
        if dummy_mode_mock.i <= 1:
            return {"cooling_mode": 1}
        else:
            return {"cooling_mode": 0}

    dummy_mode_mock.i = 0

    mocker.patch("unit_cooler.controller.engine.dummy_cooling_mode", side_effect=dummy_mode_mock)
    mocker.patch("unit_cooler.actuator.sensor.FD_Q10C.stop", side_effect=RuntimeError())

    move_to(time_machine, 0)

    component_manager.start_actuator(config, server_port, log_port, msg_count=10)
    component_manager.start_controller(config, server_port, real_port, msg_count=10)

    time.sleep(0.5)  # Reduced from 2 for testing
    move_to(time_machine, 1)
    time.sleep(0.2)  # Reduced from 1 for testing
    move_to(time_machine, 2)
    time.sleep(0.2)  # Reduced from 1 for testing
    move_to(time_machine, 3)
    time.sleep(0.2)  # Reduced from 1 for testing
    move_to(time_machine, 4)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(config)
    # NOTE: エラーが発生していなければ OK


def test_actuator_fd_q10c_stop_error(  # noqa: PLR0913
    standard_mocks, component_manager, time_machine, config, server_port, real_port, log_port
):
    import inspect

    mock_gpio(standard_mocks)
    mock_fd_q10c(standard_mocks, gen_fd_q10c_ser_trans_sense(True))

    def dummy_mode_mock():
        dummy_mode_mock.i += 1
        if dummy_mode_mock.i <= 1:
            return {"cooling_mode": 1}
        else:
            return {"cooling_mode": 0}

    dummy_mode_mock.i = 0

    standard_mocks.patch("unit_cooler.controller.engine.dummy_cooling_mode", side_effect=dummy_mode_mock)

    def com_stop_mock(spi, ser=None, is_power_off=False):  # noqa: ARG001
        if inspect.stack()[4].function == "stop":
            raise RuntimeError
        return True

    standard_mocks.patch("my_lib.sensor.ltc2874.com_stop", side_effect=com_stop_mock)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    standard_mocks.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    component_manager.start_actuator(config, server_port, log_port, msg_count=50)
    component_manager.start_controller(config, server_port, real_port, msg_count=50)

    time.sleep(5)
    move_to(time_machine, 1)
    time.sleep(3)
    move_to(time_machine, 2)
    time.sleep(3)
    move_to(time_machine, 0, 1)
    time.sleep(3)
    move_to(time_machine, 1, 1)
    time.sleep(3)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(
        config,
        {
            ("actuator", "monitor"): True,
        },
    )
    # NOTE: エラーが発生していなければ OK


@pytest.mark.order(2)
def test_actuator_fd_q10c_get_state_error(  # noqa: PLR0913
    mocker, component_manager, time_machine, config, server_port, real_port, log_port
):
    import inspect

    mock_gpio(mocker)
    mock_fd_q10c(mocker, gen_fd_q10c_ser_trans_sense(True))
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    def dummy_mode_mock():
        dummy_mode_mock.i += 1
        if dummy_mode_mock.i <= 1:
            return {"cooling_mode": 1}
        else:
            return {"cooling_mode": 0}

    dummy_mode_mock.i = 0

    mocker.patch("unit_cooler.controller.engine.dummy_cooling_mode", side_effect=dummy_mode_mock)

    def com_status_mock(spi):  # noqa: ARG001
        if inspect.stack()[4].function == "get_state":
            raise RuntimeError
        return True

    mocker.patch("my_lib.sensor.ltc2874.com_status", side_effect=com_status_mock)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    component_manager.start_actuator(config, server_port, log_port, msg_count=20)
    component_manager.start_controller(config, server_port, real_port, msg_count=20)

    time.sleep(3)
    move_to(time_machine, 1)
    time.sleep(2)
    move_to(time_machine, 2)
    time.sleep(2)
    move_to(time_machine, 0, 1)
    time.sleep(2)
    move_to(time_machine, 1, 1)
    time.sleep(2)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(config)
    # NOTE: エラーが発生していなければ OK


@pytest.mark.order(1)
def test_actuator_no_test(  # noqa: PLR0913
    mocker, component_manager, config, server_port, real_port, log_port
):
    import signal

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    mocker.patch.dict("os.environ", {"TEST": "false"})

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    component_manager.start_actuator(config, server_port, log_port, speedup=100, msg_count=2)
    component_manager.start_controller(config, server_port, real_port, speedup=100, msg_count=2)

    time.sleep(1)

    # NOTE: signal のテストもついでにやっておく
    import actuator

    actuator.sig_handler(signal.SIGKILL, None)
    actuator.sig_handler(signal.SIGTERM, None)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(config)
    # NOTE: 正常終了すれば OK


def test_actuator_unable_to_receive(  # noqa: PLR0913
    mocker, component_manager, time_machine, config, server_port, real_port, log_port
):
    mock_gpio(mocker)
    mocker.patch("unit_cooler.actuator.sensor.get_flow", return_value=0)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    component_manager.start_actuator(config, server_port, log_port, msg_count=10)

    time.sleep(2)
    move_to(time_machine, 20)

    time.sleep(1)

    component_manager.start_controller(config, server_port, real_port, msg_count=10)

    time.sleep(1)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(config)  # Both control and monitor should be healthy
    check_notify_slack("冷却モードの指示を受信できません。")


def test_actuator_open(  # noqa: PLR0913
    standard_mocks, component_manager, time_machine, config, server_port, real_port, log_port
):
    mock_gpio(standard_mocks)
    mock_fd_q10c(standard_mocks)
    standard_mocks.patch("my_lib.sensor.ltc2874.com_status", return_value=True)
    standard_mocks.patch("unit_cooler.controller.engine.dummy_cooling_mode", return_value={"cooling_mode": 1})

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    standard_mocks.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    component_manager.start_actuator(config, server_port, log_port, msg_count=15)
    component_manager.start_controller(config, server_port, real_port, msg_count=15)

    # NOTE: set_cooling_working が呼ばれるまで最大30秒待つ
    wait_for_set_cooling_working()

    time.sleep(1)  # Keep original timing for error detection
    move_to(time_machine, 1)

    time.sleep(0.5)
    move_to(time_machine, 2)

    standard_mocks.patch("unit_cooler.controller.engine.dummy_cooling_mode", return_value={"cooling_mode": 0})

    time.sleep(0.5)

    for i in range(3, 10):
        move_to(time_machine, i)
        time.sleep(0.5)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_standard_liveness(config)  # Both control and monitor should be healthy
    check_notify_slack("電磁弁が壊れていますので制御を停止します。")


def test_actuator_flow_unknown_1(  # noqa: PLR0913
    standard_mocks, component_manager, config, server_port, real_port, log_port
):
    import copy

    import unit_cooler.controller.message
    from unit_cooler.controller.message import CONTROL_MESSAGE_LIST as CONTROL_MESSAGE_LIST_ORIG

    mock_gpio(standard_mocks)
    standard_mocks.patch("unit_cooler.actuator.sensor.get_flow", return_value=None)
    standard_mocks.patch(
        "unit_cooler.controller.engine.dummy_cooling_mode",
        return_value={"cooling_mode": len(CONTROL_MESSAGE_LIST_ORIG) - 1},
    )

    message_list_orig = copy.deepcopy(CONTROL_MESSAGE_LIST_ORIG)
    message_list_orig[-1]["duty"]["on_sec"] = 100000  # 100倍速で100秒
    standard_mocks.patch.object(unit_cooler.controller.message, "CONTROL_MESSAGE_LIST", message_list_orig)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    standard_mocks.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    # NOTE: エラー閾値を下げて7回の実行でエラーが発生するようにする
    config["actuator"]["monitor"]["sense"]["giveup"] = 3

    component_manager.start_controller(
        config, server_port, real_port, speedup=100, dummy_mode=True, msg_count=7
    )
    component_manager.start_actuator(config, server_port, log_port, speedup=100, msg_count=7)

    component_manager.wait_and_term_controller()
    component_manager.wait_and_term_actuator()

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("流量計が使えません。")


def test_actuator_flow_unknown_2(mocker, config, server_port, real_port, log_port):
    import copy

    import actuator
    import controller
    import unit_cooler.controller.message
    from unit_cooler.controller.message import CONTROL_MESSAGE_LIST as CONTROL_MESSAGE_LIST_ORIG

    mock_gpio(mocker)
    mocker.patch("unit_cooler.actuator.sensor.FD_Q10C.get_value", side_effect=RuntimeError)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch(
        "unit_cooler.controller.engine.dummy_cooling_mode",
        return_value={"cooling_mode": len(CONTROL_MESSAGE_LIST_ORIG) - 1},
    )

    message_list_orig = copy.deepcopy(CONTROL_MESSAGE_LIST_ORIG)
    message_list_orig[-1]["duty"]["on_sec"] = 1000  # 100倍速で10秒
    mocker.patch.object(unit_cooler.controller.message, "CONTROL_MESSAGE_LIST", message_list_orig)

    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 10,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("流量計が使えません。")


@pytest.mark.order(9)
def test_actuator_leak(  # noqa: PLR0913
    mocker, time_machine, config, server_port, real_port, log_port
):
    import copy

    import actuator
    import controller
    import unit_cooler.controller.message
    from unit_cooler.controller.message import CONTROL_MESSAGE_LIST as CONTROL_MESSAGE_LIST_ORIG

    mock_gpio(mocker)
    mocker.patch("unit_cooler.actuator.sensor.get_flow", return_value=20)
    sense_data_mock = create_fetch_data_mock({})
    mocker.patch("my_lib.sensor_data.fetch_data", side_effect=sense_data_mock)

    # NOTE: このテストはダミーモードを使わないので、judge_cooling_mode を差し替える
    def mock_judge_cooling_mode(config, sense_data):  # noqa: ARG001
        return {
            "cooling_mode": len(CONTROL_MESSAGE_LIST_ORIG) - 1,
            "cooler_status": {"status": 1, "message": None},
            "outdoor_status": {"status": 1, "message": None},
            "sense_data": sense_data,
        }

    mocker.patch(
        "unit_cooler.controller.engine.judge_cooling_mode",
        side_effect=mock_judge_cooling_mode,
    )

    message_list_orig = copy.deepcopy(CONTROL_MESSAGE_LIST_ORIG)
    message_list_orig[-1]["duty"]["on_sec"] = 100000
    message_list_orig[-1]["duty"]["off_sec"] = 100000
    mocker.patch.object(unit_cooler.controller.message, "CONTROL_MESSAGE_LIST", message_list_orig)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 20,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 20,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    # NOTE: set_cooling_working が呼ばれるまで待つ
    wait_for_set_cooling_working()

    for i in range(1, 10):
        move_to(time_machine, i)
        time.sleep(0.5)

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True, 1000)
    check_liveness(config, ["actuator", "subscribe"], True, 1000)
    check_liveness(config, ["actuator", "control"], True, 1000)
    check_liveness(config, ["actuator", "monitor"], True, 1000)
    check_liveness(config, ["webui", "subscribe"], False)

    logging.info(my_lib.notify.slack.hist_get(False))

    assert (
        my_lib.notify.slack.hist_get(False)[-1].find("水漏れしています。") == 0
        or my_lib.notify.slack.hist_get(False)[-2].find("水漏れしています。") == 0
    )


def test_actuator_speedup(standard_mocks, config, server_port, real_port, log_port):
    import actuator
    import controller

    standard_mocks.patch("unit_cooler.actuator.sensor.get_flow", return_value=None)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 5,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 5,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_standard_liveness(config)
    # NOTE: 正常終了すれば OK


def test_actuator_monitor_error(standard_mocks, config, server_port, real_port, log_port):
    import actuator
    import controller

    standard_mocks.patch("unit_cooler.actuator.sensor.get_flow", return_value=None)
    standard_mocks.patch("unit_cooler.actuator.monitor.send_mist_condition", side_effect=RuntimeError())

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 2,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 2,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    time.sleep(2)

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_standard_liveness(
        config,
        {
            ("actuator", "monitor"): False,
        },
    )
    check_notify_slack("Traceback")


def test_actuator_slack_error(standard_mocks, config, server_port, real_port, log_port):
    import slack_sdk

    import actuator
    import controller

    standard_mocks.patch("unit_cooler.actuator.sensor.get_flow", return_value=None)

    def webclient_mock(self, token):  # noqa: ARG001
        raise slack_sdk.errors.SlackClientError

    standard_mocks.patch.object(slack_sdk.web.client.WebClient, "__init__", webclient_mock)
    standard_mocks.patch("unit_cooler.actuator.monitor.send_mist_condition", side_effect=RuntimeError())

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 2,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 2,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_standard_liveness(
        config,
        {
            ("actuator", "monitor"): False,
        },
    )
    check_notify_slack("Traceback")


def test_actuator_close(  # noqa: PLR0913
    mocker, time_machine, config, server_port, real_port, log_port
):
    import copy

    import actuator
    import controller
    import unit_cooler.controller.message
    from unit_cooler.controller.message import CONTROL_MESSAGE_LIST as CONTROL_MESSAGE_LIST_ORIG

    mock_gpio(mocker)
    mocker.patch("unit_cooler.actuator.sensor.get_flow", return_value=0)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch(
        "unit_cooler.controller.engine.dummy_cooling_mode",
        return_value={"cooling_mode": len(CONTROL_MESSAGE_LIST_ORIG) - 1},
    )
    message_list_orig = copy.deepcopy(CONTROL_MESSAGE_LIST_ORIG)
    message_list_orig[-1]["duty"]["on_sec"] = 10000  # 100倍速で100秒
    mocker.patch.object(unit_cooler.controller.message, "CONTROL_MESSAGE_LIST", message_list_orig)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 10,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "dummy_mode": True,
            "speedup": 100,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )
    move_to(time_machine, 1)
    time.sleep(2)
    move_to(time_machine, 2)
    time.sleep(2)
    move_to(time_machine, 3)
    time.sleep(2)
    move_to(time_machine, 4)
    time.sleep(2)

    actuator.wait_and_term(*actuator_handle)
    controller.wait_and_term(*control_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True, 180)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("元栓が閉じています。")


def test_actuator_emit_error(mocker, config, server_port, real_port, log_port):
    import actuator
    import controller

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    sender_mock = mocker.MagicMock()
    sender_mock.emit.return_value = False
    mocker.patch("fluent.sender.FluentSender", return_value=sender_mock)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})
    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 1,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 1,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack(None)


def test_actuator_notify_hazard(  # noqa: PLR0913
    mocker, time_machine, config, server_port, real_port, log_port
):
    import actuator
    import controller
    import unit_cooler.actuator.control

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    move_to(time_machine, 0)

    unit_cooler.actuator.control.hazard_register(config)

    move_to(time_machine, 0, 1)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 5,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 5,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    time.sleep(2)

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("過去に水漏れもしくは電磁弁の故障が検出されているので制御を停止しています。")


def test_actuator_ctrl_error(mocker, config, server_port, real_port, log_port):
    import actuator
    import controller

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    mocker.patch("unit_cooler.actuator.valve.set_cooling_state", side_effect=RuntimeError())

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 10,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], False)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("Traceback")


def test_actuator_recv_error(mocker, config, server_port, real_port, log_port):
    import actuator
    import controller
    from unit_cooler.pubsub.subscribe import start_client as start_client_orig

    mock_gpio(mocker)
    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    def start_client_mock(server_host, server_port, func, msg_count=0):
        start_client_orig(server_host, server_port, func, msg_count)
        raise RuntimeError

    mocker.patch("unit_cooler.pubsub.subscribe.start_client", side_effect=start_client_mock)

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "msg_count": 1,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack("Traceback")


def test_actuator_iolink_short(mocker, config, server_port, real_port, log_port):
    import actuator
    import controller

    mock_gpio(mocker)

    # NOTE: 流量計の故障モードを代表してテスト
    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans[3]["recv"] = fd_q10c_ser_trans[3]["recv"][0:2]
    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    # NOTE: mock で差し替えたセンサーを使わせるため、ダミーモードを取り消す
    mocker.patch.dict("os.environ", {"DUMMY_MODE": "false"})

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 5,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 5,
            "server_port": server_port,
            "real_port": real_port,
        },
    )
    time.sleep(1)
    mock_fd_q10c(mocker, gen_fd_q10c_ser_trans_sense())

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack(None)  # NOTE: 単発では通知しない


#####################################################################
def test_fd_q10c(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    # NOTE: spi_read=0x00 で、電源 OFF を返すようにする
    mock_fd_q10c(mocker, gen_fd_q10c_ser_trans_sense(), count=0, spi_read=0x00)

    assert FD_Q10C().get_value(False) is None
    assert FD_Q10C().get_value(True) == 2.57
    assert FD_Q10C().get_value_map() == {"flow": 2.57}


def test_fd_q10c_ping(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    mock_fd_q10c(mocker, gen_fd_q10c_ser_trans_ping())

    assert FD_Q10C().ping()


def test_fd_q10c_stop(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    mock_fd_q10c(mocker)
    sensor = FD_Q10C()
    sensor.stop()

    # NOTE: エラーが発生していなければ OK


def test_fd_q10c_stop_error_1(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    mocker.patch("fcntl.flock", side_effect=OSError)

    mock_fd_q10c(mocker)
    sensor = FD_Q10C()
    with pytest.raises(RuntimeError):
        sensor.stop()


def test_fd_q10c_stop_error_2(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    mocker.patch("serial.Serial.close", side_effect=OSError)

    mock_fd_q10c(mocker)
    sensor = FD_Q10C()
    sensor.stop()

    sensor.get_value()
    sensor.stop()

    # NOTE: エラーが発生していなければ OK


def test_fd_q10c_short(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans[3]["recv"] = fd_q10c_ser_trans[3]["recv"][0:2]
    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    assert FD_Q10C().get_value() is None


def test_fd_q10c_ext(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans.insert(3, {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0xD1, 0x18]})

    mock_fd_q10c(mocker, fd_q10c_ser_trans, count=10)

    assert FD_Q10C().get_value(True) is None


def test_fd_q10c_wait(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans.insert(3, {"send": [0xF0, 0x2D], "recv": [0xF0, 0x2D, 0x01, 0x3C]})

    mock_fd_q10c(mocker, fd_q10c_ser_trans, count=10)

    assert FD_Q10C().get_value(True) is None


def test_fd_q10c_checksum(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans[3]["recv"][3] = 0x11
    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    assert FD_Q10C().get_value(True) is None


def test_fd_q10c_power_on(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    mock_fd_q10c(mocker, spi_read=0x11)

    assert FD_Q10C().get_value(True) == 2.57


def test_fd_q10c_unknown_datatype(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C
    from my_lib.sensor.fd_q10c import driver as fd_q10c_driver

    mock_fd_q10c(mocker)

    assert FD_Q10C().read_param(0x94, fd_q10c_driver.DATA_TYPE_RAW, True) == [1, 1]


def test_fd_q10c_header_error(mocker):
    import inspect

    from my_lib.sensor.fd_q10c import FD_Q10C
    from my_lib.sensor.ltc2874 import msq_checksum as msq_checksum_orig

    data_injected = 0xC0
    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans[3]["recv"][2] = data_injected
    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    # NOTE: 特定の関数からの特定の引数での call の際のみ、入れ替える
    def msq_checksum_mock(data):
        if (inspect.stack()[4].function == "isdu_res_read") and (data == [data_injected]):
            return fd_q10c_ser_trans[3]["recv"][3]
        else:
            return msq_checksum_orig(data)

    mocker.patch("my_lib.sensor.ltc2874.msq_checksum", side_effect=msq_checksum_mock)

    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    assert FD_Q10C().get_value() is None


def test_fd_q10c_chk_error(mocker):
    import inspect

    from my_lib.sensor.fd_q10c import FD_Q10C
    from my_lib.sensor.ltc2874 import msq_checksum as msq_checksum_orig

    data_injected = 0xD3
    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans[6]["recv"][2] = data_injected
    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    # NOTE: 特定の関数からの特定の引数での call の際のみ、入れ替える
    def msq_checksum_mock(data):
        if (inspect.stack()[4].function == "isdu_res_read") and (data == [data_injected]):
            return fd_q10c_ser_trans[6]["recv"][3]
        else:
            return msq_checksum_orig(data)

    mocker.patch("my_lib.sensor.ltc2874.msq_checksum", side_effect=msq_checksum_mock)

    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    assert FD_Q10C().get_value() is None


def test_fd_q10c_header_invalid(mocker):
    import inspect

    from my_lib.sensor.fd_q10c import FD_Q10C
    from my_lib.sensor.ltc2874 import msq_checksum as msq_checksum_orig

    data_injected = 0x00
    fd_q10c_ser_trans = gen_fd_q10c_ser_trans_sense()
    fd_q10c_ser_trans[3]["recv"][2] = data_injected
    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    # NOTE: 特定の関数からの特定の引数での call の際のみ、入れ替える
    def msq_checksum_mock(data):
        if (inspect.stack()[4].function == "isdu_res_read") and (data == [data_injected]):
            return fd_q10c_ser_trans[3]["recv"][3]
        else:
            return msq_checksum_orig(data)

    mocker.patch("my_lib.sensor.ltc2874.msq_checksum", side_effect=msq_checksum_mock)

    mock_fd_q10c(mocker, fd_q10c_ser_trans)

    assert FD_Q10C().get_value() is None


def test_fd_q10c_timeout(mocker):
    from my_lib.sensor.fd_q10c import FD_Q10C

    mock_fd_q10c(mocker)

    mocker.patch("fcntl.flock", side_effect=OSError())

    assert FD_Q10C().get_value() is None


@pytest.mark.order(3)
def test_actuator_restart(mocker, config, server_port, real_port, log_port):
    import actuator
    import controller

    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 1,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 20,  # 2回目のactuatorにも確実にメッセージが届くように増やす
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    actuator.wait_and_term(*actuator_handle)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 1,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], False)
    check_notify_slack(None)


@pytest.mark.order(8)
def test_webui(mocker, config, server_port, real_port, log_port):  # noqa: PLR0915
    import gzip
    import re

    import actuator
    import controller
    import webui

    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100)
    mock_react_index_html(mocker)

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    app = webui.create_app(
        config, {"msg_count": 1, "pub_port": server_port, "log_port": log_port, "dummy_mode": False}
    )
    client = app.test_client()

    # NOTE: set_cooling_working が呼ばれるまで待つ
    wait_for_set_cooling_working()

    res = client.get("/")
    assert res.status_code == 302
    assert re.search(rf"{my_lib.webapp.config.URL_PREFIX}/$", res.location)

    res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/")
    assert res.status_code == 200
    assert "室外機" in res.data.decode("utf-8")

    res = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/",
        headers={"Accept-Encoding": "gzip"},
    )
    assert res.status_code == 200
    assert "室外機" in gzip.decompress(res.data).decode("utf-8")

    # Wait for logs to be committed to database
    time.sleep(5)

    # Temporarily override DUMMY_MODE to avoid stop_day=7
    with unittest.mock.patch.dict(os.environ, {"DUMMY_MODE": "false"}):
        res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/proxy/json/api/log_view")
        assert res.status_code == 200
        assert "data" in res.json
        assert len(res.json["data"]) != 0
        assert "last_time" in res.json

    res = client.get(
        f"{my_lib.webapp.config.URL_PREFIX}/api/proxy/event/api/event", query_string={"count": "2"}
    )
    assert res.status_code == 200
    assert res.data.decode()

    res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/stat")
    assert res.status_code == 200
    assert "watering" in res.json
    assert "sensor" in res.json
    assert "mode" in res.json
    assert "cooler_status" in res.json
    assert "outdoor_status" in res.json

    # NOTE: mock を戻す手間を避けるため，最後に実施
    response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/proxy/json/api/log_view")
    assert response.status_code == 200
    assert "data" in response.json
    assert "last_time" in response.json

    client.delete()

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], True)
    check_notify_slack(None)


def test_webui_dummy_mode(standard_mocks, config, server_port, real_port, log_port):
    import actuator
    import controller
    import webui

    standard_mocks.patch("my_lib.sensor_data.get_day_sum", return_value=100)

    # Start controller first to ensure actuator receives messages immediately
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )
    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )

    # Use msg_count: 1 to ensure worker thread exits quickly after receiving a message
    app = webui.create_app(
        config, {"msg_count": 2, "dummy_mode": True, "pub_port": server_port, "log_port": log_port}
    )
    client = app.test_client()

    # Wait for services to initialize and worker to receive its message
    time.sleep(2)

    res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/stat")
    assert res.status_code == 200
    assert "watering" in res.json
    assert "sensor" in res.json
    assert "mode" in res.json
    assert "cooler_status" in res.json
    assert "outdoor_status" in res.json

    with unittest.mock.patch(
        "flask.wrappers.Response.status_code",
        return_value=301,
        new_callable=unittest.mock.PropertyMock,
    ):
        res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/", headers={"Accept-Encoding": "gzip"})
        assert res.status_code == 301

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    # Give worker thread time to exit cleanly after receiving its message
    time.sleep(0.5)

    client.delete()

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], True)
    check_notify_slack(None)


def test_webui_queue_overflow(mocker, config, server_port, real_port, log_port):
    import pathlib

    import actuator
    import controller
    import unit_cooler.webui.worker
    import webui

    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())
    mocker.patch("my_lib.sensor_data.get_day_sum", return_value=100)

    mocker.patch.dict("os.environ", {"DUMMY_MODE": "true"})

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 5,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "msg_count": 5,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    app = webui.create_app(
        config, {"msg_count": 2, "dummy_mode": False, "pub_port": server_port, "log_port": log_port}
    )
    client = app.test_client()

    # NOTE: カバレッジ用にキューを溢れさせる
    for _ in range(30):
        unit_cooler.webui.worker.queue_put(
            app.config["MESSAGE_QUEUE"],
            {"state": 0},
            pathlib.Path(config["webui"]["subscribe"]["liveness"]["file"]),
        )
        time.sleep(0.01)

    res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/stat")
    assert res.status_code == 200
    assert "watering" in res.json
    assert "sensor" in res.json
    assert "mode" in res.json
    assert "cooler_status" in res.json
    assert "outdoor_status" in res.json

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    client.delete()

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], True)
    check_notify_slack(None)


def test_webui_day_sum(mocker, config, server_port, real_port, log_port):
    import actuator
    import controller
    import webui

    fetch_data_mock = mocker.MagicMock()
    fetch_data_mock.to_values.side_effect = [[[None, 10]], [], RuntimeError()]

    mock_fd_q10c(mocker)
    mocker.patch("my_lib.sensor_data.fetch_data_impl", return_value=fetch_data_mock)
    mocker.patch("my_lib.sensor_data.fetch_data", return_value=gen_sense_data())

    actuator_handle = actuator.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "pub_port": server_port,
            "log_port": log_port,
        },
    )
    control_handle = controller.start(
        config,
        {
            "speedup": 100,
            "dummy_mode": True,
            "msg_count": 10,
            "server_port": server_port,
            "real_port": real_port,
        },
    )

    time.sleep(1)

    app = webui.create_app(
        config, {"msg_count": 1, "dummy_mode": True, "pub_port": server_port, "log_port": log_port}
    )
    client = app.test_client()

    res = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/stat")
    assert res.status_code == 200
    assert "watering" in res.json
    assert "sensor" in res.json
    assert "mode" in res.json
    assert "cooler_status" in res.json
    assert "outdoor_status" in res.json

    controller.wait_and_term(*control_handle)
    actuator.wait_and_term(*actuator_handle)

    client.delete()

    check_liveness(config, ["controller"], True)
    check_liveness(config, ["actuator", "subscribe"], True)
    check_liveness(config, ["actuator", "control"], True)
    check_liveness(config, ["actuator", "monitor"], True)
    check_liveness(config, ["webui", "subscribe"], True)
    check_notify_slack(None)
