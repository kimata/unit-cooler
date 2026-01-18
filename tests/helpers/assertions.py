#!/usr/bin/env python3
# ruff: noqa: S101
"""カスタムアサーションヘルパー"""

from __future__ import annotations

import logging
import pathlib
from typing import TYPE_CHECKING

import my_lib.footprint

if TYPE_CHECKING:
    from unit_cooler.config import Config


class LivenessChecker:
    """Liveness チェックヘルパー

    コンポーネントの healthz ファイルを確認する。
    """

    DEFAULT_THRESHOLD_SEC = 120

    def __init__(self, config: Config):
        """初期化

        Args:
            config: アプリケーション設定
        """
        self.config = config

    def _get_liveness_file(self, component_path: list[str]) -> pathlib.Path:
        """コンポーネントパスから liveness ファイルパスを取得

        Args:
            component_path: コンポーネントパス (例: ["controller"], ["actuator", "control"])

        Returns:
            liveness ファイルのパス
        """
        # コンポーネントパスから明示的にマッピング
        if component_path == ["controller"]:
            return pathlib.Path(self.config.controller.liveness.file)
        elif component_path == ["actuator", "subscribe"]:
            return pathlib.Path(self.config.actuator.subscribe.liveness.file)
        elif component_path == ["actuator", "control"]:
            return pathlib.Path(self.config.actuator.control.liveness.file)
        elif component_path == ["actuator", "monitor"]:
            return pathlib.Path(self.config.actuator.monitor.liveness.file)
        elif component_path == ["webui", "subscribe"]:
            return pathlib.Path(self.config.webui.subscribe.liveness.file)
        else:
            raise ValueError(f"未知のコンポーネントパス: {component_path}")

    def assert_healthy(
        self,
        component_path: list[str],
        threshold_sec: int | None = None,
    ) -> None:
        """コンポーネントが健全であることを確認

        Args:
            component_path: コンポーネントパス (例: ["controller"], ["actuator", "control"])
            threshold_sec: 閾値秒数

        Raises:
            AssertionError: コンポーネントが不健全な場合
        """
        if threshold_sec is None:
            threshold_sec = self.DEFAULT_THRESHOLD_SEC

        liveness_file = self._get_liveness_file(component_path)

        elapsed = my_lib.footprint.elapsed(liveness_file)
        assert (elapsed < threshold_sec) is True, (
            f"{'/'.join(component_path)} の healthz が更新されていません。"
            f"(経過時間: {elapsed:.1f}秒, 閾値: {threshold_sec}秒)"
        )

    def assert_unhealthy(self, component_path: list[str]) -> None:
        """コンポーネントが不健全であることを確認

        Args:
            component_path: コンポーネントパス

        Raises:
            AssertionError: コンポーネントが健全な場合
        """
        liveness_file = self._get_liveness_file(component_path)

        elapsed = my_lib.footprint.elapsed(liveness_file)
        assert elapsed >= self.DEFAULT_THRESHOLD_SEC, (
            f"{'/'.join(component_path)} が予想に反して健全です。(経過時間: {elapsed:.1f}秒)"
        )

    def check_standard_liveness(self, include_controller: bool = True) -> None:
        """標準的な liveness チェックを実行

        Args:
            include_controller: コントローラーも確認する場合 True
        """
        if include_controller:
            self.assert_healthy(["controller"])

        self.assert_healthy(["actuator", "subscribe"])
        self.assert_healthy(["actuator", "control"])
        self.assert_healthy(["actuator", "monitor"])
        self.assert_healthy(["webui", "subscribe"])

    def check_controller_only_liveness(self) -> None:
        """コントローラーのみの liveness チェック"""
        self.assert_healthy(["controller"])
        self.assert_unhealthy(["actuator", "subscribe"])
        self.assert_unhealthy(["actuator", "control"])
        self.assert_unhealthy(["actuator", "monitor"])
        self.assert_unhealthy(["webui", "subscribe"])


class SlackChecker:
    """Slack 通知チェックヘルパー"""

    def __init__(self):
        """初期化"""
        pass

    @staticmethod
    def get_history(is_thread_local: bool = False) -> list[str]:
        """通知履歴を取得

        Args:
            is_thread_local: スレッドローカルの履歴を取得する場合 True

        Returns:
            通知メッセージのリスト
        """
        import my_lib.notify.slack

        return my_lib.notify.slack._hist_get(is_thread_local)

    def assert_notified(self, message: str, index: int = -1) -> None:
        """特定のメッセージが通知されたことを確認

        Args:
            message: 期待するメッセージ (部分一致)
            index: 履歴のインデックス (デフォルト: 最後)

        Raises:
            AssertionError: メッセージが通知されていない場合
        """
        notify_hist = self.get_history()
        logging.debug("Slack notification history: %s", notify_hist)

        assert len(notify_hist) != 0, "異常が発生したはずなのに、エラー通知がされていません。"
        assert notify_hist[index].find(message) != -1, (
            f"「{message}」が Slack で通知されていません。実際の通知: {notify_hist[index]}"
        )

    def assert_not_notified(self) -> None:
        """通知がされていないことを確認

        Raises:
            AssertionError: 通知がされている場合
        """
        notify_hist = self.get_history()
        assert notify_hist == [], f"正常なはずなのに、エラー通知がされています。通知内容: {notify_hist}"

    def assert_any_notified(self) -> None:
        """何らかの通知がされていることを確認

        Raises:
            AssertionError: 通知がされていない場合
        """
        notify_hist = self.get_history()
        assert len(notify_hist) > 0, "通知が1件も送信されていません。"

    def clear_history(self) -> None:
        """通知履歴をクリア"""
        import my_lib.notify.slack

        my_lib.notify.slack._hist_clear()


class WorkLogChecker:
    """作業ログチェックヘルパー"""

    def __init__(self):
        """初期化"""
        pass

    @staticmethod
    def get_history() -> list[str]:
        """作業ログ履歴を取得

        Returns:
            ログメッセージのリスト
        """
        import unit_cooler.actuator.work_log

        return unit_cooler.actuator.work_log.hist_get()

    def assert_logged(self, message: str) -> None:
        """特定のメッセージがログに記録されたことを確認

        Args:
            message: 期待するメッセージ (部分一致)

        Raises:
            AssertionError: メッセージがログに記録されていない場合
        """
        work_log_hist = self.get_history()
        logging.debug("Work log history: %s", work_log_hist)

        assert len(work_log_hist) != 0, "作業ログが1件も記録されていません。"

        found = any(msg.find(message) != -1 for msg in work_log_hist)
        assert found, f"「{message}」が work_log で通知されていません。実際のログ: {work_log_hist}"

    def assert_not_logged(self) -> None:
        """作業ログが記録されていないことを確認

        Raises:
            AssertionError: ログが記録されている場合
        """
        work_log_hist = self.get_history()
        assert work_log_hist == [], f"正常なはずなのに、作業ログが記録されています。ログ内容: {work_log_hist}"

    def clear_history(self) -> None:
        """作業ログ履歴をクリア"""
        import unit_cooler.actuator.work_log

        unit_cooler.actuator.work_log.hist_clear()


class ValveStateChecker:
    """バルブ状態チェックヘルパー"""

    def __init__(self):
        """初期化"""
        pass

    @staticmethod
    def assert_open() -> None:
        """バルブが開いていることを確認"""
        import unit_cooler.actuator.valve_controller
        from unit_cooler.const import VALVE_STATE

        state = unit_cooler.actuator.valve_controller.get_valve_controller().get_state()
        assert state == VALVE_STATE.OPEN, f"バルブが開いていません。現在の状態: {state}"

    @staticmethod
    def assert_closed() -> None:
        """バルブが閉じていることを確認"""
        import unit_cooler.actuator.valve_controller
        from unit_cooler.const import VALVE_STATE

        state = unit_cooler.actuator.valve_controller.get_valve_controller().get_state()
        assert state == VALVE_STATE.CLOSE, f"バルブが閉じていません。現在の状態: {state}"
