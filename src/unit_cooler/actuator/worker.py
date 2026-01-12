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
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import my_lib.footprint

import unit_cooler.actuator.control
import unit_cooler.actuator.monitor
import unit_cooler.actuator.status_publisher
import unit_cooler.actuator.work_log
import unit_cooler.const
import unit_cooler.pubsub.subscribe
import unit_cooler.util

if TYPE_CHECKING:
    from multiprocessing import Queue

    from my_lib.lifecycle import LifecycleManager

    from unit_cooler.config import Config


# =============================================================================
# WorkerState: テスト同期用のイベントベース状態管理
# =============================================================================
@dataclass
class WorkerState:
    """ワーカー状態管理（テスト同期用）

    ワーカーの処理完了を通知し、テストコードで待機できるようにする。
    time.sleep() を使わずに確実な同期を実現する。

    threading.Condition を使用して process_count ベースの待機を実装。
    これにより、特定の処理回数に達するまで待つことが可能。
    """

    process_count: int = 0
    last_process_time: datetime | None = None
    _condition: threading.Condition = field(default_factory=threading.Condition, init=False)

    def notify_processed(self) -> None:
        """処理完了を通知

        ワーカーが1回の処理ループを完了した際に呼び出す。
        wait_for_process() や wait_for_count() で待機しているスレッドに通知される。
        """
        with self._condition:
            self.process_count += 1
            self.last_process_time = datetime.now()
            self._condition.notify_all()

    def wait_for_process(self, timeout: float = 1.0) -> bool:
        """次の処理完了を待機

        現在の process_count から +1 されるまで待機する。

        Args:
            timeout: 最大待機時間（秒）

        Returns:
            処理完了通知を受け取った場合 True、タイムアウトした場合 False
        """
        with self._condition:
            target = self.process_count + 1
            return self._condition.wait_for(
                lambda: self.process_count >= target,
                timeout=timeout,
            )

    def wait_for_count(self, target_count: int, timeout: float = 1.0) -> bool:
        """特定の処理回数に達するまで待機

        Args:
            target_count: 待機する処理回数
            timeout: 最大待機時間（秒）

        Returns:
            目標回数に達した場合 True、タイムアウトした場合 False
        """
        with self._condition:
            return self._condition.wait_for(
                lambda: self.process_count >= target_count,
                timeout=timeout,
            )

    def get_count(self) -> int:
        """現在の処理回数を取得"""
        with self._condition:
            return self.process_count

    def reset(self) -> None:
        """状態をリセット"""
        with self._condition:
            self.process_count = 0
            self.last_process_time = None


# =============================================================================
# グローバル状態管理（pytestワーカー毎に独立）
# =============================================================================
# グローバル辞書（pytestワーカー毎に独立）
_control_messages: dict[str, dict[str, Any]] = {}
_should_terminate: dict[str, threading.Event] = {}
_worker_states: dict[str, dict[str, WorkerState]] = {}

# LifecycleManager インスタンス（オプション）
_lifecycle_manager: LifecycleManager | None = None

# メッセージの初期値
MESSAGE_INIT = {"mode_index": 0, "state": unit_cooler.const.COOLING_STATE.IDLE}


def set_lifecycle_manager(manager: LifecycleManager | None) -> None:
    """LifecycleManager を設定する"""
    global _lifecycle_manager
    _lifecycle_manager = manager


def get_lifecycle_manager() -> LifecycleManager | None:
    """LifecycleManager を取得する"""
    return _lifecycle_manager


def get_worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "")


def get_last_control_message():
    """グローバル辞書からlast_control_messageを取得"""
    worker_id = get_worker_id()
    if worker_id not in _control_messages:
        set_last_control_message(MESSAGE_INIT.copy())

    return _control_messages[worker_id]


def set_last_control_message(message):
    """グローバル辞書にlast_control_messageを設定"""
    _control_messages[get_worker_id()] = message


def get_should_terminate() -> threading.Event | None:
    """終了イベントを取得する

    LifecycleManager が設定されている場合はその termination_event を返し、
    そうでない場合はグローバル辞書から取得する。
    """
    if _lifecycle_manager is not None:
        return _lifecycle_manager.termination_event
    return _should_terminate.get(get_worker_id(), None)


def init_should_terminate() -> None:
    """終了イベントを初期化する

    LifecycleManager が設定されている場合は reset() を呼び、
    そうでない場合はグローバル辞書に新しいイベントを作成する。
    """
    if _lifecycle_manager is not None:
        _lifecycle_manager.reset()
        return

    should_terminate = _should_terminate.get(get_worker_id())

    if should_terminate is None:
        _should_terminate[get_worker_id()] = threading.Event()
    else:
        should_terminate.clear()


# =============================================================================
# WorkerState アクセス関数
# =============================================================================
def get_worker_state(worker_name: str) -> WorkerState:
    """指定したワーカーの WorkerState を取得する

    Args:
        worker_name: ワーカー名（"control_worker", "monitor_worker" など）

    Returns:
        指定したワーカーの WorkerState インスタンス
    """
    worker_id = get_worker_id()
    if worker_id not in _worker_states:
        _worker_states[worker_id] = {}
    if worker_name not in _worker_states[worker_id]:
        _worker_states[worker_id][worker_name] = WorkerState()
    return _worker_states[worker_id][worker_name]


def init_worker_states() -> None:
    """全ワーカーの WorkerState を初期化/リセットする"""
    worker_id = get_worker_id()
    if worker_id in _worker_states:
        for state in _worker_states[worker_id].values():
            state.reset()
    else:
        _worker_states[worker_id] = {}


def wait_for_control_process(timeout: float = 1.0) -> bool:
    """control_worker の処理完了を待機する（テスト用便利関数）"""
    return get_worker_state("control_worker").wait_for_process(timeout)


def wait_for_monitor_process(timeout: float = 1.0) -> bool:
    """monitor_worker の処理完了を待機する（テスト用便利関数）"""
    return get_worker_state("monitor_worker").wait_for_process(timeout)


# =============================================================================
# StateManager への通知（オプション）
# =============================================================================
def _notify_state_manager_control_processed() -> None:
    """StateManager に control_worker の処理完了を通知"""
    try:
        from unit_cooler.state_manager import get_state_manager

        get_state_manager().notify_control_processed()
    except Exception:
        logging.debug("StateManager notification failed (control_processed)")


def _notify_state_manager_monitor_processed() -> None:
    """StateManager に monitor_worker の処理完了を通知"""
    try:
        from unit_cooler.state_manager import get_state_manager

        get_state_manager().notify_monitor_processed()
    except Exception:
        logging.debug("StateManager notification failed (monitor_processed)")


def collect_environmental_metrics(config: Config, current_message: dict[str, Any]) -> None:
    """環境データのメトリクス収集"""
    from unit_cooler.metrics import get_metrics_collector

    try:
        metrics_db_path = config.actuator.metrics.data
        metrics_collector = get_metrics_collector(metrics_db_path)

        # current_messageのsense_dataからセンサーデータを取得
        sense_data = current_message.get("sense_data", {})

        if sense_data:
            # 各センサーデータの最新値を取得
            temperature = None
            humidity = None
            lux = None
            solar_radiation = None
            rain_amount = None

            if sense_data.get("temp") and len(sense_data["temp"]) > 0:
                temperature = sense_data["temp"][0].get("value")
            if sense_data.get("humi") and len(sense_data["humi"]) > 0:
                humidity = sense_data["humi"][0].get("value")
            if sense_data.get("lux") and len(sense_data["lux"]) > 0:
                lux = sense_data["lux"][0].get("value")
            if sense_data.get("solar_rad") and len(sense_data["solar_rad"]) > 0:
                solar_radiation = sense_data["solar_rad"][0].get("value")
                logging.debug("Solar radiation data found: %s W/m²", solar_radiation)
            else:
                logging.debug(
                    "No solar radiation data in sense_data: %s",
                    list(sense_data.keys()) if sense_data else "empty",
                )
            if sense_data.get("rain") and len(sense_data["rain"]) > 0:
                rain_amount = sense_data["rain"][0].get("value")

            # 環境データをメトリクスに記録
            metrics_collector.update_environmental_data(
                temperature, humidity, lux, solar_radiation, rain_amount
            )

    except Exception:
        logging.exception("Failed to collect environmental metrics")


def queue_put(message_queue, message, liveness_file):
    message["state"] = unit_cooler.const.COOLING_STATE(message["state"])

    logging.info("Receive message: %s", message)

    message_queue.put(message)
    my_lib.footprint.update(liveness_file)


def sleep_until_next_iter(start_time, interval_sec):
    sleep_sec = max(interval_sec - (time.time() - start_time), 0.5)
    logging.debug("Seep %.1f sec...", sleep_sec)

    # should_terminate が設定されるまで待機（最大 sleep_sec 秒）
    get_should_terminate().wait(timeout=sleep_sec)


# NOTE: コントローラから制御指示を受け取ってキューに積むワーカ
def subscribe_worker(
    config: Config,
    control_host: str,
    pub_port: int,
    message_queue: Queue[Any],
    liveness_file: pathlib.Path,
    msg_count: int = 0,
) -> int:
    logging.info("Start actuator subscribe worker (%s:%d)", control_host, pub_port)
    ret = 0
    try:
        unit_cooler.pubsub.subscribe.start_client(
            control_host,
            pub_port,
            lambda message: queue_put(message_queue, message, liveness_file),
            msg_count,
        )
    except Exception:
        logging.exception("Failed to receive control message")
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1

    logging.warning("Stop subscribe worker")
    return ret


# NOTE: バルブの状態をモニタするワーカ
def monitor_worker(
    config: Config,
    liveness_file: pathlib.Path,
    dummy_mode: bool = False,
    speedup: int = 1,
    msg_count: int = 0,
    status_pub_port: int = 0,
) -> int:
    logging.info("Start monitor worker")

    interval_sec = config.actuator.monitor.interval_sec / speedup
    try:
        handle = unit_cooler.actuator.monitor.gen_handle(config, interval_sec)
    except Exception:
        logging.exception("Failed to create handle")

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
            logging.exception("Failed to create status publisher")

    i = 0
    ret = 0
    try:
        while True:
            start_time = time.time()

            need_logging = (i % handle["log_period"]) == 0
            i += 1

            mist_condition = unit_cooler.actuator.monitor.get_mist_condition()
            unit_cooler.actuator.monitor.check(handle, mist_condition, need_logging)
            unit_cooler.actuator.monitor.send_mist_condition(
                handle, mist_condition, get_last_control_message(), dummy_mode
            )

            # ActuatorStatus を ZeroMQ で配信
            if status_socket is not None:
                try:
                    status = unit_cooler.actuator.status_publisher.create_status(
                        mist_condition, get_last_control_message()
                    )
                    unit_cooler.actuator.status_publisher.publish_status(status_socket, status)
                except Exception:
                    logging.debug("Failed to publish ActuatorStatus")

            my_lib.footprint.update(liveness_file)

            # テスト用: 処理完了を通知
            get_worker_state("monitor_worker").notify_processed()
            _notify_state_manager_monitor_processed()

            if get_should_terminate().is_set():
                logging.info("Terminate monitor worker")
                break

            if msg_count != 0:
                logging.debug("(monitor_count, msg_count) = (%d, %d)", handle["monitor_count"], msg_count)
                # NOTE: monitor_worker が先に終了しないようにする
                if handle["monitor_count"] >= (msg_count + 20):
                    logging.info(
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
                logging.debug("Failed to close status publisher")

    logging.warning("Stop monitor worker")
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
    logging.info("Start control worker")

    if dummy_mode:
        logging.warning("DUMMY mode")

    interval_sec = config.actuator.control.interval_sec / speedup
    handle = unit_cooler.actuator.control.gen_handle(config, message_queue)

    ret = 0
    try:
        while True:
            start_time = time.time()

            current_message = unit_cooler.actuator.control.get_control_message(
                handle, get_last_control_message()
            )

            set_last_control_message(current_message)

            unit_cooler.actuator.control.execute(config, current_message)

            # 環境データのメトリクス収集（定期的に実行）
            try:
                collect_environmental_metrics(config, current_message)
            except Exception:
                logging.debug("Failed to collect environmental metrics")

            my_lib.footprint.update(liveness_file)

            # テスト用: 処理完了を通知
            get_worker_state("control_worker").notify_processed()
            _notify_state_manager_control_processed()

            if get_should_terminate().is_set():
                logging.info("Terminate control worker")
                break

            if msg_count != 0:
                logging.debug("(receive_count, msg_count) = (%d, %d)", handle["receive_count"], msg_count)
                if handle["receive_count"] >= msg_count:
                    logging.info("Terminate control, because the specified number of times has been reached.")
                    break

            sleep_until_next_iter(start_time, interval_sec)
    except Exception:
        logging.exception("Failed to control valve")
        unit_cooler.util.notify_error(config, traceback.format_exc())
        ret = -1

    logging.warning("Stop control worker")
    # NOTE: Queue を close した後に put されると ValueError が発生するので、
    # 明示的に閉じるのをやめた。
    # message_queue.close()

    return ret


def get_worker_def(
    config: Config, message_queue: Queue[Any], setting: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "name": "subscribe_worker",
            "param": [
                subscribe_worker,
                config,
                setting["control_host"],
                setting["pub_port"],
                message_queue,
                pathlib.Path(config.actuator.subscribe.liveness.file),
                setting["msg_count"],
            ],
        },
        {
            "name": "monitor_worker",
            "param": [
                monitor_worker,
                config,
                pathlib.Path(config.actuator.monitor.liveness.file),
                setting["dummy_mode"],
                setting["speedup"],
                setting["msg_count"],
                setting.get("status_pub_port", 0),
            ],
        },
        {
            "name": "control_worker",
            "param": [
                control_worker,
                config,
                message_queue,
                pathlib.Path(config.actuator.control.liveness.file),
                setting["dummy_mode"],
                setting["speedup"],
                setting["msg_count"],
            ],
        },
    ]


def start(executor, worker_def):
    init_should_terminate()
    init_worker_states()
    thread_list = []

    for worker_info in worker_def:
        future = executor.submit(*worker_info["param"])
        thread_list.append({"name": worker_info["name"], "future": future})

        # LifecycleManager が設定されている場合はワーカーを登録
        if _lifecycle_manager is not None:
            _lifecycle_manager.register_worker(worker_info["name"], future)

    return thread_list


def term() -> None:
    """終了をリクエストする

    LifecycleManager が設定されている場合は request_termination() を呼び、
    そうでない場合はグローバルイベントを set する。
    """
    logging.info("Terminate actuator worker")
    if _lifecycle_manager is not None:
        _lifecycle_manager.request_termination()
    else:
        event = get_should_terminate()
        if event is not None:
            event.set()


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import docopt
    import my_lib.logger
    import my_lib.webapp.config
    import my_lib.webapp.log

    import unit_cooler.actuator.valve
    from unit_cooler.config import Config

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    control_host = os.environ.get("HEMS_CONTROL_HOST", args["-s"])
    pub_port = int(os.environ.get("HEMS_PUB_PORT", args["-p"]))
    speedup = int(args["-t"])
    msg_count = int(args["-n"])
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)
    message_queue = multiprocessing.Queue()
    event_queue = multiprocessing.Queue()

    os.environ["DUMMY_MODE"] = "true"

    my_lib.webapp.config.init(config.actuator.web_server.webapp.to_webapp_config())
    my_lib.webapp.log.init(config.actuator.web_server.webapp.to_webapp_config())
    unit_cooler.actuator.work_log.init(config, event_queue)

    unit_cooler.actuator.valve.init(config.actuator.control.valve.pin_no, config)
    unit_cooler.actuator.monitor.init(config.actuator.control.valve.pin_no)

    # NOTE: テストしやすいように、threading.Thread ではなく multiprocessing.pool.ThreadPool を使う
    executor = concurrent.futures.ThreadPoolExecutor()

    setting = {
        "control_host": control_host,
        "pub_port": pub_port,
        "speedup": speedup,
        "msg_count": msg_count,
        "dummy_mode": True,
    }

    thread_list = start(executor, get_worker_def(config, message_queue, setting))

    for thread_info in thread_list:
        logging.info("Wait %s finish", thread_info["name"])

        if thread_info["future"].result() != 0:
            logging.warning("Error occurred in %s", thread_info["name"])

    unit_cooler.actuator.work_log.term()

    logging.info("Shutdown executor")
    executor.shutdown()
