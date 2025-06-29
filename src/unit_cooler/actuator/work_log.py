#!/usr/bin/env python3
"""
作動ログを記録します。主にテストで使用します。

Usage:
  work_log.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import logging

import my_lib.webapp.event
import my_lib.webapp.log

import unit_cooler.const
import unit_cooler.util

config = None
enven_queue = None

log_hist = []


def init(config_, event_queue_):
    global config  # noqa: PLW0603
    global event_queue  # noqa: PLW0603

    config = config_
    event_queue = event_queue_


def term():
    global event_queue
    my_lib.webapp.log.term()


# NOTE: テスト用
def hist_clear():
    global log_hist  # noqa: PLW0603

    log_hist = []


# NOTE: テスト用
def hist_get():
    global log_hist

    return log_hist


def add(message, level=unit_cooler.const.LOG_LEVEL.INFO):
    global log_hist
    global config
    global event_queue

    event_queue.put(my_lib.webapp.event.EVENT_TYPE.LOG)
    my_lib.webapp.log.add(message, level)

    log_hist.append(message)

    if level == unit_cooler.const.LOG_LEVEL.ERROR:
        unit_cooler.util.notify_error(config, message)
        # エラーメトリクス記録
        try:
            from unit_cooler.actuator.webapi.metrics import record_error

            record_error("work_log_error", message)
        except ImportError:
            pass
    elif level == unit_cooler.const.LOG_LEVEL.WARN:
        # 警告メトリクス記録
        try:
            from unit_cooler.actuator.webapi.metrics import record_warning

            record_warning("work_log_warning", message)
        except ImportError:
            pass


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty
    import my_lib.webapp.config

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)
    event_queue = multiprocessing.Queue()

    my_lib.webapp.config.init(config["actuator"])
    my_lib.webapp.log.init(config)
    init(config, event_queue)

    add("Test", unit_cooler.const.LOG_LEVEL.INFO)
    add("Test", unit_cooler.const.LOG_LEVEL.WARN)
    add("Test", unit_cooler.const.LOG_LEVEL.ERROR)

    logging.info(my_lib.pretty.format(hist_get()))

    term()
