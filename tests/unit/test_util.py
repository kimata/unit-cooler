#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.util のテスト"""

import logging
import unittest.mock

from unit_cooler.util import notify_error


class TestNotifyError:
    """notify_error のテスト"""

    def test_logs_error(self, config, caplog):
        """エラーログを出力"""
        with (
            caplog.at_level(logging.ERROR),
            unittest.mock.patch("my_lib.notify.slack.error"),
        ):
            notify_error(config, "Test error message")

        assert "Test error message" in caplog.text

    def test_no_logging_when_disabled(self, config, caplog):
        """is_logging=False の場合はログ出力しない"""
        with (
            caplog.at_level(logging.ERROR),
            unittest.mock.patch("my_lib.notify.slack.error"),
        ):
            notify_error(config, "Test error message", is_logging=False)

        assert "Test error message" not in caplog.text

    def test_skips_slack_in_dummy_mode(self, config):
        """ダミーモードでは Slack 通知しない"""
        with (
            unittest.mock.patch.dict("os.environ", {"TEST": "false", "DUMMY_MODE": "true"}),
            unittest.mock.patch("my_lib.notify.slack.error") as mock_slack,
        ):
            notify_error(config, "Test error")

        mock_slack.assert_not_called()

    def test_sends_slack_in_test_mode(self, config):
        """テストモードでは Slack 通知する"""
        with (
            unittest.mock.patch.dict("os.environ", {"TEST": "true", "DUMMY_MODE": "false"}),
            unittest.mock.patch("my_lib.notify.slack.error") as mock_slack,
        ):
            notify_error(config, "Test error")

        mock_slack.assert_called_once()

    def test_handles_slack_error(self, config, caplog):
        """Slack 通知エラーをハンドリング"""
        with (
            unittest.mock.patch.dict("os.environ", {"TEST": "true"}),
            unittest.mock.patch(
                "my_lib.notify.slack.error",
                side_effect=Exception("Slack error"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            notify_error(config, "Test error")

        assert "Failed to Notify via Slack" in caplog.text
