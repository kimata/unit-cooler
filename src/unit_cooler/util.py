#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import traceback
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

import my_lib.notify.slack

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config


P = ParamSpec("P")
T = TypeVar("T")


def notify_error(config: Config, message: str, is_logging: bool = True) -> None:
    if is_logging:
        logger.error(message)

    if isinstance(config.slack, my_lib.notify.slack.SlackEmptyConfig) or (
        (os.environ.get("TEST", "false") != "true") and (os.environ.get("DUMMY_MODE", "false") == "true")
    ):
        # NOTE: テストではなく、ダミーモードで実行している時は Slack 通知しない
        return

    try:
        my_lib.notify.slack.error(config.slack, "室外機冷却システム", message)
    except Exception:
        logger.exception("Failed to Notify via Slack")


def handle_worker_error(
    config: Config,
    error_message: str = "Worker failed",
    notify: bool = True,
    reraise: bool = False,
    default_return: T | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T | None]]:
    """ワーカーエラーハンドリングデコレータ

    ワーカー関数のエラーハンドリングを統一するデコレータ。
    例外発生時のログ出力、Slack 通知、例外の再送出を設定可能。

    Args:
        config: アプリケーション設定（Slack 通知に使用）
        error_message: ログに出力するエラーメッセージ
        notify: Slack 通知を行うかどうか（default: True）
        reraise: 例外を再送出するかどうか（default: False）
        default_return: 例外時のデフォルト戻り値（default: None）

    Returns:
        デコレータ関数

    Example:
        @handle_worker_error(config, "Failed to control valve", notify=True)
        def execute(config: Config, control_message: dict) -> None:
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T | None]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
            try:
                return func(*args, **kwargs)
            except Exception:
                logger.exception(error_message)
                if notify:
                    notify_error(config, traceback.format_exc(), is_logging=False)
                if reraise:
                    raise
                return default_return

        return wrapper

    return decorator


def safe_call(
    func: Callable[P, T],
    error_message: str = "Operation failed",
    default_return: T | None = None,
) -> Callable[P, T | None]:
    """簡易エラーハンドリングラッパー

    Slack 通知不要で、単純にエラーをキャッチしてログ出力したい場合に使用。

    Args:
        func: ラップする関数
        error_message: ログに出力するエラーメッセージ
        default_return: 例外時のデフォルト戻り値

    Returns:
        ラップされた関数

    Example:
        safe_func = safe_call(risky_operation, "Failed to perform operation", default_return=0)
        result = safe_func()
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception(error_message)
            return default_return

    return wrapper
