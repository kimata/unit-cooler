#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import my_lib.notify.slack

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config


def notify_error(config: Config, message: str, is_logging: bool = True) -> None:
    if is_logging:
        logger.error(message)

    # NOTE: テストではなく、ダミーモードで実行している時は Slack 通知しない
    if (os.environ.get("TEST", "false") != "true") and (os.environ.get("DUMMY_MODE", "false") == "true"):
        return

    try:
        # my_lib.notify.slack.error() は SlackEmptyConfig の場合は何もしない
        my_lib.notify.slack.error(config.slack, "室外機冷却システム", message)
    except Exception:
        logger.exception("Failed to Notify via Slack")
