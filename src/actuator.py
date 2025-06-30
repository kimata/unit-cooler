#!/usr/bin/env python3
"""
電磁弁を制御してエアコン室外機の冷却を行います。

Usage:
  actuator.py [-c CONFIG] [-s CONTROL_HOST] [-p PUB_PORT] [-n COUNT] [-d] [-t SPEEDUP] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。 [default: config.yaml]
  -s CONTROL_HOST   : コントローラのホスト名を指定します。 [default: localhost]
  -p PUB_PORT       : ZeroMQ の Pub サーバーを動作させるポートを指定します。 [default: 2222]
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

SCHEMA_CONFIG = "config.schema"


def sig_handler(num, frame):  # noqa: ARG001
    import unit_cooler.actuator.worker

    logging.warning("Receive signal %d", num)

    if num == signal.SIGTERM:
        unit_cooler.actuator.worker.term()


def wait_before_start(config):
    for i in range(config["actuator"]["control"]["interval_sec"]):
        logging.info(
            "Wait for the old Pod to finish (%3d / %3d)", i + 1, config["actuator"]["control"]["interval_sec"]
        )
        time.sleep(1)


def start(config, arg):
    global should_terminate  # noqa: PLW0603
    global log_server_handle  # noqa: PLW0603

    setting = {
        "control_host": "localhost",
        "pub_port": 2222,
        "log_port": 5001,
        "dummy_mode": False,
        "speedup": 1,
        "msg_count": 0,
        "debug_mode": False,
    }
    setting.update(arg)

    should_terminate = False

    logging.info("Using ZMQ server of %s:%d", setting["control_host"], setting["pub_port"])

    # NOTE: オプションでダミーモードが指定された場合、環境変数もそれに揃えておく
    if setting["dummy_mode"]:
        logging.warning("Set dummy mode")
        os.environ["DUMMY_MODE"] = "true"

    manager = multiprocessing.Manager()
    message_queue = manager.Queue()
    event_queue = manager.Queue()

    # NOTE: Blueprint のパス指定を YAML で行いたいので、my_lib.webapp の import 順を制御
    import unit_cooler.actuator.web_server

    log_server_handle = unit_cooler.actuator.web_server.start(config, event_queue, setting["log_port"])

    if not setting["dummy_mode"] and (os.environ.get("TEST", "false") != "true"):
        # NOTE: 動作開始前に待つ。これを行わないと、複数の Pod が電磁弁を制御することに
        # なり、電磁弁の故障を誤判定する可能性がある。
        wait_before_start(config)

    import unit_cooler.actuator.work_log
    import unit_cooler.actuator.worker

    unit_cooler.actuator.work_log.init(config, event_queue)

    logging.info("Initialize valve")
    unit_cooler.actuator.valve.init(config["actuator"]["control"]["valve"]["pin_no"])
    unit_cooler.actuator.monitor.init(config["actuator"]["control"]["valve"]["pin_no"])

    executor = concurrent.futures.ThreadPoolExecutor()

    thread_list = unit_cooler.actuator.worker.start(
        executor, unit_cooler.actuator.worker.get_worker_def(config, message_queue, setting)
    )

    signal.signal(signal.SIGTERM, sig_handler)

    return (executor, thread_list, log_server_handle)


def wait_and_term(executor, thread_list, log_server_handle, terminate=True):
    global should_terminate  # noqa: PLW0603

    import unit_cooler.actuator.web_server
    import unit_cooler.actuator.work_log

    should_terminate = terminate

    ret = 0
    for thread_info in thread_list:
        logging.info("Wait %s finish", thread_info["name"])

        if thread_info["future"].result() != 0:
            logging.error("Error occurred in %s", thread_info["name"])
            ret = -1

    logging.info("Shutdown executor")
    executor.shutdown(wait=True)

    unit_cooler.actuator.web_server.term(log_server_handle)
    unit_cooler.actuator.work_log.term()

    logging.warning("Terminate unit_cooler")

    return ret


######################################################################
if __name__ == "__main__":
    import pathlib
    import sys

    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    control_host = os.environ.get("HEMS_CONTROL_HOST", args["-s"])
    pub_port = int(os.environ.get("HEMS_PUB_PORT", args["-p"]))
    dummy_mode = os.environ.get("DUMMY_MODE", args["-d"])
    speedup = int(args["-t"])
    msg_count = int(args["-n"])
    debug_mode = args["-D"]

    my_lib.logger.init("hems.unit_cooler", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file, pathlib.Path(SCHEMA_CONFIG))

    sys.exit(
        wait_and_term(
            *start(
                config,
                {
                    "control_host": control_host,
                    "pub_port": pub_port,
                    "log_port": config["actuator"]["web_server"]["webapp"]["port"],
                    "dummy_mode": dummy_mode,
                    "speedup": speedup,
                    "msg_count": msg_count,
                    "debug_mode": debug_mode,
                },
            ),
            terminate=False,
        )
    )
