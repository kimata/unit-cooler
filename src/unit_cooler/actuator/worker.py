#!/usr/bin/env python3
"""
アクチュエータで動作するワーカです。

Usage:
  worker.py [-c CONFIG] [-s CONTROL_HOST] [-p PUB_PORT] [-n COUNT] [-t SPEEDUP] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -s CONTROL_HOST   : コントローラのホスト名を指定します。 [default: localhost]
  -p PUB_PORT       : ZeroMQ の Pub サーバーを動作させるポートを指定します。 [default: 2222]
  -n COUNT          : n 回制御メッセージを受信したら終了します。0 は制限なし。 [default: 1]
  -t SPEEDUP        : 時短モード。演算間隔を SPEEDUP 分の一にします。 [default: 1]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import pathlib
import threading
import time
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import my_lib.time

import unit_cooler.actuator.control
import unit_cooler.actuator.monitor
import unit_cooler.actuator.status_publisher
import unit_cooler.actuator.work_log
import unit_cooler.const
import unit_cooler.pubsub.subscribe
import unit_cooler.util
from unit_cooler.messages import ControlMessage, DutyConfig

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config, RuntimeSettings


@dataclass
class WorkerDef:
    """ワーカー定義"""

    name: str
    param: list[Any]


# =============================================================================
# グローバル状態管理（pytestワーカー毎に独立）
# =============================================================================
# グローバル辞書（pytestワーカー毎に独立）
_control_messages: dict[str, ControlMessage] = {}
_should_terminate: dict[str, threading.Event] = {}

# メッセージの初期値
MESSAGE_INIT = ControlMessage(
    state=unit_cooler.const.COOLING_STATE.IDLE,
    duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
    mode_index=0,
)


def get_worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "")


def get_last_control_message() -> ControlMessage:
    """グローバル辞書からlast_control_messageを取得"""
    worker_id = get_worker_id()
    if worker_id not in _control_messages:
        set_last_control_message(MESSAGE_INIT)

    return _control_messages[worker_id]


def set_last_control_message(message: ControlMessage) -> None:
    """グローバル辞書にlast_control_messageを設定"""
    _control_messages[get_worker_id()] = message


def get_should_terminate() -> threading.Event | None:
    """終了イベントを取得する"""
    return _should_terminate.get(get_worker_id(), None)


def init_should_terminate() -> None:
    """終了イベントを初期化する"""
    should_terminate = _should_terminate.get(get_worker_id())

    if should_terminate is None:
        _should_terminate[get_worker_id()] = threading.Event()
    else:
        should_terminate.clear()


def collect_environmental_metrics(config: Config, current_message: ControlMessage) -> None:
    """環境データのメトリクス収集"""
    from unit_cooler.metrics import get_metrics_collector

    sense_data = current_message.sense_data
    if sense_data is None:
        return

    try:
        metrics_collector = get_metrics_collector(config.actuator.metrics.data)
        metrics_collector.update_environmental_data(
            temperature=sense_data.first_value("temp"),
            humidity=sense_data.first_value("humi"),
            lux=sense_data.first_value("lux"),
            solar_radiation=sense_data.first_value("solar_rad"),
            rain_amount=sense_data.first_value("rain"),
        )
    except Exception:
        logger.exception("Failed to collect environmental metrics")


def collect_flow_metrics(config: Config, mist_condition: unit_cooler.actuator.monitor.MistCondition) -> None:
    """バルブ ON 中の流量をメトリクスに記録する"""
    if mist_condition.valve.state != unit_cooler.const.VALVE_STATE.OPEN or mist_condition.flow is None:
        return

    from unit_cooler.metrics import get_metrics_collector

    try:
        get_metrics_collector(config.actuator.metrics.data).update_flow_value(mist_condition.flow)
    except Exception:
        logger.exception("Failed to collect flow metrics")


def sleep_until_next_iter(start_time, interval_sec):
    sleep_sec = max(interval_sec - (time.monotonic() - start_time), 0.5)
    logger.debug("Sleep %.1f sec...", sleep_sec)

    # should_terminate が設定されるまで待機（最大 sleep_sec 秒）
    should_terminate = get_should_terminate()
    if should_terminate is not None:
        should_terminate.wait(timeout=sleep_sec)
    else:
        time.sleep(sleep_sec)


# NOTE: コントローラから制御指示を受け取ってキューに積むワーカ
def subscribe_worker(
    config: Config,
    control_host: str,
    pub_port: int,
    message_queue: Queue[Any],
    liveness_file: pathlib.Path,
    msg_count: int = 0,
    should_terminate: threading.Event | None = None,
) -> int:
    return unit_cooler.pubsub.subscribe.run_subscribe_worker(
        config,
        "actuator",
        control_host,
        pub_port,
        lambda message: unit_cooler.pubsub.subscribe.queue_put(message_queue, message, liveness_file),
        msg_count,
        should_terminate,
    )


# NOTE: バルブの状態をモニタするワーカ
def monitor_worker(
    config: Config,
    liveness_file: pathlib.Path,
    dummy_mode: bool = False,
    speedup: int = 1,
    msg_count: int = 0,
    status_pub_port: int = 0,
) -> int:
    logger.info("Start monitor worker")

    interval_sec = config.actuator.monitor.interval_sec / speedup
    try:
        handle = unit_cooler.actuator.monitor.gen_handle(config, interval_sec)
    except Exception:
        logger.exception("Failed to create handle")

        unit_cooler.actuator.work_log.add(
            "流量のロギングを開始できません。", unit_cooler.const.LOG_LEVEL.ERROR
        )
        return -1

    # ActuatorStatus 配信用の ZeroMQ パブリッシャを作成
    status_socket = None
    if status_pub_port > 0:
        try:
            status_socket = unit_cooler.actuator.status_publisher.create_publisher("*", status_pub_port)
        except Exception:
            logger.exception("Failed to create status publisher")

    i = 0
    ret = 0
    try:
        while True:
            start_time = time.monotonic()

            need_logging = (i % handle.log_period) == 0
            i += 1

            mist_condition = unit_cooler.actuator.monitor.get_mist_condition()
            unit_cooler.actuator.monitor.check(handle, mist_condition, need_logging)
            unit_cooler.actuator.monitor.send_mist_condition(
                handle, mist_condition, get_last_control_message(), dummy_mode
            )
            collect_flow_metrics(config, mist_condition)

            # ActuatorStatus を ZeroMQ で配信
            if status_socket is not None:
                try:
                    status = unit_cooler.actuator.status_publisher.create_status(
                        mist_condition, get_last_control_message()
                    )
                    unit_cooler.actuator.status_publisher.publish_status(status_socket, status)
                except Exception:
                    logger.debug("Failed to publish ActuatorStatus")

            my_lib.footprint.update(liveness_file)

            terminate_event = get_should_terminate()
            if terminate_event is not None and terminate_event.is_set():
                logger.info("Terminate monitor worker")
                break

            if msg_count != 0:
                logger.debug("(monitor_count, msg_count) = (%d, %d)", handle.monitor_count, msg_count)
                # NOTE: monitor_worker が先に終了しないようにする
                if handle.monitor_count >= (msg_count + 20):
                    logger.info(
                        "Terminate monitor worker, because the specified number of times has been reached."
                    )
                    break

            sleep_until_next_iter(start_time, interval_sec)
    except Exception:
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1
    finally:
        # ソケットをクローズ
        if status_socket is not None:
            try:
                unit_cooler.actuator.status_publisher.close_publisher(status_socket)
            except Exception:
                logger.debug("Failed to close status publisher")

    logger.warning("Stop monitor worker")
    return ret


# NOTE: バルブを制御するワーカ
def control_worker(
    config: Config,
    message_queue: Queue[Any],
    liveness_file: pathlib.Path,
    dummy_mode: bool = False,
    speedup: int = 1,
    msg_count: int = 0,
) -> int:
    logger.info("Start control worker")

    if dummy_mode:
        logger.warning("DUMMY mode")

    interval_sec = config.actuator.control.interval_sec / speedup
    handle = unit_cooler.actuator.control.gen_handle(config, message_queue)

    ret = 0
    try:
        while True:
            start_time = time.monotonic()

            current_message = unit_cooler.actuator.control.get_control_message(
                handle, get_last_control_message()
            )

            set_last_control_message(current_message)

            unit_cooler.actuator.control.execute(config, current_message)

            # 環境データのメトリクス収集（定期的に実行）
            try:
                collect_environmental_metrics(config, current_message)
            except Exception:
                logger.debug("Failed to collect environmental metrics")

            my_lib.footprint.update(liveness_file)

            terminate_event = get_should_terminate()
            if terminate_event is not None and terminate_event.is_set():
                logger.info("Terminate control worker")
                break

            if msg_count != 0:
                logger.debug("(receive_count, msg_count) = (%d, %d)", handle.receive_count, msg_count)
                if handle.receive_count >= msg_count:
                    logger.info("Terminate control, because the specified number of times has been reached.")
                    break

            sleep_until_next_iter(start_time, interval_sec)
    except Exception:
        logger.exception("Failed to control valve")
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1

    logger.warning("Stop control worker")
    # NOTE: Queue を close した後に put されると ValueError が発生するので、
    # 明示的に閉じるのをやめた。
    # message_queue.close()

    return ret


def get_worker_def(config: Config, message_queue: Queue[Any], settings: RuntimeSettings) -> list[WorkerDef]:
    return [
        WorkerDef(
            name="subscribe_worker",
            param=[
                subscribe_worker,
                config,
                settings.control_host,
                settings.pub_port,
                message_queue,
                config.actuator.subscribe.liveness.file,
                settings.msg_count,
            ],
        ),
        WorkerDef(
            name="monitor_worker",
            param=[
                monitor_worker,
                config,
                config.actuator.monitor.liveness.file,
                settings.dummy_mode,
                settings.speedup,
                settings.msg_count,
                settings.status_pub_port,
            ],
        ),
        WorkerDef(
            name="control_worker",
            param=[
                control_worker,
                config,
                message_queue,
                config.actuator.control.liveness.file,
                settings.dummy_mode,
                settings.speedup,
                settings.msg_count,
            ],
        ),
    ]


def start(executor, worker_def: list[WorkerDef]):
    init_should_terminate()
    thread_list = []

    for worker_info in worker_def:
        # subscribe_worker には should_terminate を追加で渡す
        params = list(worker_info.param)
        if worker_info.name == "subscribe_worker":
            params.append(get_should_terminate())
        future = executor.submit(*params)
        thread_list.append({"name": worker_info.name, "future": future})

    return thread_list


def term() -> None:
    """終了をリクエストする"""
    logger.info("Terminate actuator worker")
    event = get_should_terminate()
    if event is not None:
        event.set()


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import my_lib.webapp.config
    import my_lib.webapp.log

    import unit_cooler.actuator.valve_controller
    import unit_cooler.cli
    import unit_cooler.const
    from unit_cooler.config import RuntimeSettings

    assert __doc__ is not None  # noqa: S101
    args, config = unit_cooler.cli.init(__doc__, name="test")

    settings = RuntimeSettings.from_args(
        args,
        {
            "control_host": "-s",
            "pub_port": "-p",
            "speedup": "-t",
            "msg_count": "-n",
        },
    )
    settings.dummy_mode = True

    message_queue: multiprocessing.Queue = multiprocessing.Queue()
    event_queue: multiprocessing.Queue = multiprocessing.Queue()

    os.environ["DUMMY_MODE"] = "true"

    webapp_config = config.actuator.web_server.webapp.to_webapp_config(config.base_dir)
    my_lib.webapp.config.build_environment(webapp_config, url_prefix=unit_cooler.const.URL_PREFIX)
    assert webapp_config.data is not None  # noqa: S101
    assert webapp_config.data.log_file_path is not None  # noqa: S101
    my_lib.webapp.log.init(config.slack, webapp_config.data.log_file_path)
    unit_cooler.actuator.work_log.init(config, event_queue)

    unit_cooler.actuator.valve_controller.init_valve_controller(config, config.actuator.control.valve.pin_no)
    unit_cooler.actuator.monitor.init(config.actuator.control.valve.pin_no)

    # NOTE: テストしやすいように、threading.Thread ではなく multiprocessing.pool.ThreadPool を使う
    executor = concurrent.futures.ThreadPoolExecutor()

    thread_list = start(executor, get_worker_def(config, message_queue, settings))

    for thread_info in thread_list:
        logger.info("Wait %s finish", thread_info["name"])

        if thread_info["future"].result() != 0:
            logger.warning("Error occurred in %s", thread_info["name"])

    unit_cooler.actuator.work_log.term()

    logger.info("Shutdown executor")
    executor.shutdown()
