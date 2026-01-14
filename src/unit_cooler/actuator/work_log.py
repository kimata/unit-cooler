#!/usr/bin/env python3
"""
作動ログを記録します。主にテストで使用します。

Usage:
  work_log.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import my_lib.webapp.event
import my_lib.webapp.log

import unit_cooler.const
import unit_cooler.util

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

config: Config | None = None
event_queue: Queue[Any] | None = None

log_hist: list[str] = []


def init(config_: Config, event_queue_: Queue[Any]) -> None:
    global config
    global event_queue

    config = config_
    event_queue = event_queue_


def term():
    global event_queue
    my_lib.webapp.log.term()


# NOTE: テスト用
def hist_clear():
    global log_hist

    log_hist = []


# NOTE: テスト用
def hist_get():
    global log_hist

    return log_hist


def add(message: str, level: unit_cooler.const.LOG_LEVEL = unit_cooler.const.LOG_LEVEL.INFO) -> None:
    global log_hist
    global config
    global event_queue

    if event_queue is not None:
        event_queue.put(my_lib.webapp.event.EVENT_TYPE.LOG)
    my_lib.webapp.log.add(message, level)  # type: ignore[arg-type]

    log_hist.append(message)

    if level == unit_cooler.const.LOG_LEVEL.ERROR and config is not None:
        unit_cooler.util.notify_error(config, message)


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import docopt
    import my_lib.logger
    import my_lib.pretty
    import my_lib.webapp.config

    from unit_cooler.config import Config

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)
    event_queue = multiprocessing.Queue()

    my_lib.webapp.config.init(config.actuator.web_server.webapp.to_webapp_config())
    my_lib.webapp.log.init(config.actuator.web_server.webapp.to_webapp_config())  # type: ignore[arg-type]
    init(config, event_queue)

    add("Test", unit_cooler.const.LOG_LEVEL.INFO)
    add("Test", unit_cooler.const.LOG_LEVEL.WARN)
    add("Test", unit_cooler.const.LOG_LEVEL.ERROR)

    logging.info(my_lib.pretty.format(hist_get()))

    term()
