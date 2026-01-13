#!/usr/bin/env python3
"""
電磁弁を制御してエアコン室外機の冷却を行います。

Usage:
  actuator.py [-c CONFIG] [-s CONTROL_HOST] [-p PUB_PORT] [-l LOG_PORT] [-S STATUS_PORT]
              [-n COUNT] [-d] [-t SPEEDUP] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -s CONTROL_HOST   : コントローラのホスト名を指定します。 [default: localhost]
  -p PUB_PORT       : コントローラの ZeroMQ Pub サーバーのポートを指定します。 [default: 2222]
  -l LOG_PORT       : 動作ログを提供する WEB サーバーのポートを指定します。 [default: 5001]
  -S STATUS_PORT    : ActuatorStatus を配信するポートを指定します。0 で無効。 [default: 0]
  -n COUNT          : n 回制御メッセージを受信したら終了します。0 は制限なし。 [default: 0]
  -d                : ダミーモードで実行します。
  -t SPEEDUP        : 時短モード。演算間隔を SPEEDUP 分の一にします。 [default: 1]
  -D                : デバッグモードで動作します。
"""

import concurrent.futures
import logging
import multiprocessing
import os
import signal
import time
from typing import Any

from unit_cooler.config import Config, RuntimeSettings

SCHEMA_CONFIG = "config.schema"

# Global variable for web server handle
log_server_handle: Any = None


def sig_handler(num, frame):
    import unit_cooler.actuator.worker

    logging.warning("Receive signal %d", num)

    if num in (signal.SIGTERM, signal.SIGINT):
        unit_cooler.actuator.worker.term()


def wait_before_start(config: Config) -> None:
    for i in range(config.actuator.control.interval_sec):
        logging.info(
            "Wait for the old Pod to finish (%3d / %3d)", i + 1, config.actuator.control.interval_sec
        )
        time.sleep(1)


def start(config: Config, settings: RuntimeSettings) -> tuple[Any, list[Any], Any]:
    global log_server_handle

    logging.info("Using ZMQ server of %s:%d", settings.control_host, settings.pub_port)

    # NOTE: オプションでダミーモードが指定された場合、環境変数もそれに揃えておく
    if settings.dummy_mode:
        logging.warning("Set dummy mode")
        os.environ["DUMMY_MODE"] = "true"

    manager = multiprocessing.Manager()
    message_queue = manager.Queue()
    event_queue = manager.Queue()

    if not settings.dummy_mode and (os.environ.get("TEST", "false") != "true"):
        # NOTE: 動作開始前に待つ。これを行わないと、複数の Pod が電磁弁を制御することに
        # なり、電磁弁の故障を誤判定する可能性がある。
        wait_before_start(config)

    import unit_cooler.actuator.monitor
    import unit_cooler.actuator.valve
    import unit_cooler.actuator.work_log
    import unit_cooler.actuator.worker

    unit_cooler.actuator.work_log.init(config, event_queue)  # type: ignore[arg-type]

    logging.info("Initialize valve")
    unit_cooler.actuator.valve.init(config.actuator.control.valve.pin_no, config)
    unit_cooler.actuator.monitor.init(config.actuator.control.valve.pin_no)

    # NOTE: Blueprint のパス指定を YAML で行いたいので、my_lib.webapp の import 順を制御
    import unit_cooler.actuator.web_server

    try:
        logging.info("Starting web server on port %d", settings.log_port)
        log_server_handle = unit_cooler.actuator.web_server.start(
            config,
            event_queue,  # type: ignore[arg-type]
            settings.log_port,
        )
        logging.info("Web server started successfully")
    except Exception:
        logging.exception("Failed to start web server")
        raise

    executor = concurrent.futures.ThreadPoolExecutor()

    thread_list = unit_cooler.actuator.worker.start(
        executor,
        unit_cooler.actuator.worker.get_worker_def(config, message_queue, settings),  # type: ignore[arg-type]
    )

    signal.signal(signal.SIGTERM, sig_handler)

    return (executor, thread_list, log_server_handle)


def wait_and_term(executor, thread_list, log_server_handle, terminate=True):
    import unit_cooler.actuator.web_server
    import unit_cooler.actuator.work_log

    ret = 0
    for thread_info in thread_list:
        logging.info("Wait %s finish", thread_info["name"])

        if thread_info["future"].result() != 0:
            logging.error("Error occurred in %s", thread_info["name"])
            ret = -1

    unit_cooler.actuator.worker.term()

    logging.info("Shutdown executor")
    executor.shutdown(wait=True)

    # メトリクスコレクターのクローズ
    from unit_cooler.metrics import get_metrics_collector

    try:
        metrics_collector = get_metrics_collector()
        metrics_collector.close()
    except Exception:
        logging.exception("Failed to close metrics collector")

    unit_cooler.actuator.web_server.term(log_server_handle)
    unit_cooler.actuator.work_log.term()

    logging.warning("Terminate unit_cooler")

    return ret


######################################################################
if __name__ == "__main__":
    import pathlib
    import sys

    import docopt
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    control_host = os.environ.get("HEMS_CONTROL_HOST", args["-s"])
    pub_port = int(os.environ.get("HEMS_PUB_PORT", args["-p"]))
    log_port = int(os.environ.get("HEMS_LOG_PORT", args["-l"]))
    status_pub_port = int(os.environ.get("HEMS_STATUS_PUB_PORT", args["-S"]))
    dummy_mode = os.environ.get("DUMMY_MODE", args["-d"])
    speedup = int(args["-t"])
    msg_count = int(args["-n"])
    debug_mode = args["-D"]

    my_lib.logger.init("hems.unit_cooler", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file, pathlib.Path(SCHEMA_CONFIG))
    settings = RuntimeSettings.from_dict(
        {
            "control_host": control_host,
            "pub_port": pub_port,
            "log_port": log_port,
            "status_pub_port": status_pub_port,
            "dummy_mode": dummy_mode,
            "speedup": speedup,
            "msg_count": msg_count,
            "debug_mode": debug_mode,
        }
    )
    sys.exit(
        wait_and_term(
            *start(config, settings),
            terminate=False,
        )
    )
