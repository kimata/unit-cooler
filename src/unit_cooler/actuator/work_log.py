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

import collections
import logging
import time
from typing import TYPE_CHECKING, Any

import my_lib.webapp.event
import my_lib.webapp.log

import unit_cooler.const
import unit_cooler.util

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

# NOTE: テスト用の履歴。本番でも add される度に伸び続けないよう上限を設ける。
LOG_HIST_MAX = 1000

config: Config | None = None
event_queue: Queue[Any] | None = None

log_hist: collections.deque[str] = collections.deque(maxlen=LOG_HIST_MAX)

# 同一メッセージの抑制管理（抑制キー → 最終記録時刻 [time.monotonic() ベース]）
_last_add_time: dict[str, float] = {}


def init(config_: Config, event_queue_: Queue[Any]) -> None:
    global config
    global event_queue

    config = config_
    event_queue = event_queue_


def term() -> None:
    my_lib.webapp.log.term()


# NOTE: テスト用
def hist_clear() -> None:
    log_hist.clear()
    _last_add_time.clear()


# NOTE: テスト用
def hist_get() -> list[str]:
    return list(log_hist)


def _record_error_metrics(message: str) -> None:
    """エラーイベントをメトリクス DB に記録する"""
    assert config is not None  # noqa: S101

    try:
        from unit_cooler.metrics import get_metrics_collector

        get_metrics_collector(config.actuator.metrics.data).record_error(message)
    except Exception:
        logger.debug("Failed to record error metrics")


def _should_suppress(key: str, suppress_interval_min: int) -> bool:
    """同一メッセージの抑制間隔内かどうかを判定し、最終記録時刻を更新する"""
    now_monotonic = time.monotonic()
    last_add = _last_add_time.get(key)

    if last_add is not None and (now_monotonic - last_add) <= suppress_interval_min * 60:
        return True

    _last_add_time[key] = now_monotonic
    return False


def add(
    message: str,
    level: unit_cooler.const.LOG_LEVEL = unit_cooler.const.LOG_LEVEL.INFO,
    suppress_interval_min: int | None = None,
    suppress_key: str | None = None,
) -> None:
    """作動ログを記録する

    Args:
        message: 記録するメッセージ
        level: ログレベル（ERROR の場合は Slack 通知とメトリクス記録も行う）
        suppress_interval_min: 指定した場合、同一メッセージ（suppress_key 単位）の記録を
            この間隔〔分〕に 1 回に抑制する
        suppress_key: 抑制の判定キー。メッセージに可変値（流量等）が含まれる場合に指定する。
            省略時は message 全体をキーとする。
    """
    if suppress_interval_min is not None and _should_suppress(
        suppress_key if suppress_key is not None else message, suppress_interval_min
    ):
        logger.debug("Suppress work log (interval=%d min): %s", suppress_interval_min, message)
        return

    if event_queue is not None:
        event_queue.put(my_lib.webapp.event.EVENT_TYPE.LOG)
    my_lib.webapp.log.add(message, level)

    log_hist.append(message)

    if level == unit_cooler.const.LOG_LEVEL.ERROR and config is not None:
        unit_cooler.util.notify_error(config, message)
        _record_error_metrics(message)
