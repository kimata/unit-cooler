#!/usr/bin/env python3
import logging
import os

import my_lib.notify.slack

from unit_cooler.config import Config


def notify_error(config: Config, message: str, is_logging: bool = True) -> None:
    if is_logging:
        logging.error(message)

    if isinstance(config.slack, my_lib.notify.slack.SlackEmptyConfig) or (
        (os.environ.get("TEST", "false") != "true") and (os.environ.get("DUMMY_MODE", "false") == "true")
    ):
        # NOTE: テストではなく、ダミーモードで実行している時は Slack 通知しない
        return

    try:
        my_lib.notify.slack.error(config.slack, "室外機冷却システム", message)
    except Exception:
        logging.exception("Failed to Notify via Slack")
