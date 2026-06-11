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

logger = logging.getLogger(__name__)

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


def term() -> None:
    global event_queue
    my_lib.webapp.log.term()


# NOTE: テスト用
def hist_clear() -> None:
    global log_hist

    log_hist = []


# NOTE: テスト用
def hist_get() -> list[str]:
    global log_hist

    return log_hist


def add(message: str, level: unit_cooler.const.LOG_LEVEL = unit_cooler.const.LOG_LEVEL.INFO) -> None:
    global log_hist
    global config
    global event_queue

    if event_queue is not None:
        event_queue.put(my_lib.webapp.event.EVENT_TYPE.LOG)
    my_lib.webapp.log.add(message, level)

    log_hist.append(message)

    if level == unit_cooler.const.LOG_LEVEL.ERROR and config is not None:
        unit_cooler.util.notify_error(config, message)
