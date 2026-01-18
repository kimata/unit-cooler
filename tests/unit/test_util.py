#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.util のテスト"""

import logging
import unittest.mock

import pytest

from unit_cooler.util import handle_worker_error, notify_error, safe_call


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


class TestHandleWorkerError:
    """handle_worker_error デコレータのテスト"""

    def test_returns_result_on_success(self, config):
        """正常時は結果を返す"""

        @handle_worker_error(config, "Test error")
        def successful_func():
            return 42

        result = successful_func()
        assert result == 42

    def test_returns_default_on_error(self, config):
        """エラー時はデフォルト値を返す"""

        @handle_worker_error(config, "Test error", default_return=-1)
        def failing_func():
            raise ValueError("Test exception")

        result = failing_func()
        assert result == -1

    def test_returns_none_by_default_on_error(self, config):
        """エラー時のデフォルトは None"""

        @handle_worker_error(config, "Test error")
        def failing_func():
            raise ValueError("Test exception")

        result = failing_func()
        assert result is None

    def test_logs_error_on_exception(self, config, caplog):
        """例外時にログを出力"""
        with unittest.mock.patch("my_lib.notify.slack.error"):

            @handle_worker_error(config, "Worker failed")
            def failing_func():
                raise ValueError("Test exception")

            with caplog.at_level(logging.ERROR):
                failing_func()

        assert "Worker failed" in caplog.text

    def test_notifies_slack_on_error(self, config):
        """エラー時に Slack 通知"""
        with (
            unittest.mock.patch.dict("os.environ", {"TEST": "true"}),
            unittest.mock.patch("my_lib.notify.slack.error") as mock_slack,
        ):

            @handle_worker_error(config, "Test error", notify=True)
            def failing_func():
                raise ValueError("Test exception")

            failing_func()

        mock_slack.assert_called_once()

    def test_skips_slack_when_notify_false(self, config):
        """notify=False の場合は Slack 通知しない"""
        with (
            unittest.mock.patch.dict("os.environ", {"TEST": "true"}),
            unittest.mock.patch("my_lib.notify.slack.error") as mock_slack,
        ):

            @handle_worker_error(config, "Test error", notify=False)
            def failing_func():
                raise ValueError("Test exception")

            failing_func()

        mock_slack.assert_not_called()

    def test_reraises_when_requested(self, config):
        """reraise=True の場合は例外を再送出"""

        @handle_worker_error(config, "Test error", reraise=True, notify=False)
        def failing_func():
            raise ValueError("Test exception")

        with pytest.raises(ValueError, match="Test exception"):
            failing_func()

    def test_preserves_function_metadata(self, config):
        """関数のメタデータを保持"""

        @handle_worker_error(config, "Test error")
        def documented_func():
            """This is a docstring."""
            return True

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a docstring."


class TestSafeCall:
    """safe_call のテスト"""

    def test_returns_result_on_success(self):
        """正常時は結果を返す"""

        def add(a, b):
            return a + b

        safe_add = safe_call(add, "Addition failed")
        result = safe_add(2, 3)
        assert result == 5

    def test_returns_default_on_error(self):
        """エラー時はデフォルト値を返す"""

        def divide(a, b):
            return a / b

        safe_divide = safe_call(divide, "Division failed", default_return=0)
        result = safe_divide(1, 0)
        assert result == 0

    def test_returns_none_by_default_on_error(self):
        """エラー時のデフォルトは None"""

        def failing():
            raise ValueError("fail")

        safe_failing = safe_call(failing, "Failed")
        result = safe_failing()
        assert result is None

    def test_logs_error(self, caplog):
        """エラー時にログを出力"""

        def failing():
            raise ValueError("Test exception")

        safe_failing = safe_call(failing, "Operation failed")

        with caplog.at_level(logging.ERROR):
            safe_failing()

        assert "Operation failed" in caplog.text

    def test_passes_args_and_kwargs(self):
        """引数を正しく渡す"""

        def func(a, b, c=0):
            return a + b + c

        safe_func = safe_call(func, "Failed")
        result = safe_func(1, 2, c=3)
        assert result == 6

    def test_preserves_function_metadata(self):
        """関数のメタデータを保持"""

        def documented_func():
            """This is a docstring."""
            return True

        safe_func = safe_call(documented_func, "Failed")
        assert safe_func.__name__ == "documented_func"  # ty: ignore[unresolved-attribute]
        assert safe_func.__doc__ == "This is a docstring."

    def test_catches_various_exceptions(self):
        """様々な例外をキャッチ"""

        def raise_runtime():
            raise RuntimeError("runtime")

        def raise_type():
            raise TypeError("type")

        def raise_key():
            raise KeyError("key")

        assert safe_call(raise_runtime, "err", default_return=-1)() == -1
        assert safe_call(raise_type, "err", default_return=-2)() == -2
        assert safe_call(raise_key, "err", default_return=-3)() == -3
