#!/usr/bin/env python3
"""時間操作ユーティリティ

テスト用の時間操作・待機ヘルパーを提供する。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


class TimeHelper:
    """時間操作ヘルパー

    テストにおける時間関連の操作を簡素化する。
    """

    def __init__(self):
        """初期化"""
        self.frozen_time: datetime | None = None
        self.time_mock: MagicMock | None = None

    def freeze(self, mocker: MockerFixture, at: datetime | None = None) -> MagicMock:
        """時間を固定する

        Args:
            mocker: pytest-mock の mocker fixture
            at: 固定する時刻 (省略時は現在時刻)

        Returns:
            time.time のモックオブジェクト
        """
        self.frozen_time = at or datetime.now()
        timestamp = self.frozen_time.timestamp()

        self.time_mock = mocker.patch("time.time", return_value=timestamp)
        return self.time_mock

    def advance(self, seconds: float) -> None:
        """固定時間を進める

        Args:
            seconds: 進める秒数
        """
        if self.frozen_time is None:
            raise RuntimeError("Time is not frozen. Call freeze() first.")

        self.frozen_time += timedelta(seconds=seconds)
        if self.time_mock:
            self.time_mock.return_value = self.frozen_time.timestamp()

    def unfreeze(self) -> None:
        """時間の固定を解除"""
        self.frozen_time = None
        self.time_mock = None

    @staticmethod
    def wait_until(
        condition: Callable[[], bool],
        timeout: float = 10.0,
        interval: float = 0.1,
        message: str = "Condition not met within timeout",
    ) -> bool:
        """条件が満たされるまで待機

        Args:
            condition: チェックする条件関数
            timeout: タイムアウト秒数
            interval: チェック間隔秒数
            message: タイムアウト時のメッセージ

        Returns:
            条件が満たされた場合 True

        Raises:
            TimeoutError: タイムアウトした場合
        """
        start = time.time()
        while time.time() - start < timeout:
            if condition():
                return True
            time.sleep(interval)

        raise TimeoutError(f"{message} (timeout={timeout}s)")

    @staticmethod
    def wait_for_value(
        getter: Callable[[], object],
        expected: object,
        timeout: float = 10.0,
        interval: float = 0.1,
    ) -> bool:
        """値が期待値になるまで待機

        Args:
            getter: 値を取得する関数
            expected: 期待する値
            timeout: タイムアウト秒数
            interval: チェック間隔秒数

        Returns:
            期待値になった場合 True

        Raises:
            TimeoutError: タイムアウトした場合
        """
        return TimeHelper.wait_until(
            lambda: getter() == expected,
            timeout=timeout,
            interval=interval,
            message=f"Value did not become {expected}",
        )

    @staticmethod
    def wait_for_file_update(
        file_path: str,
        max_age_sec: float = 120.0,
        timeout: float = 30.0,
        interval: float = 1.0,
    ) -> bool:
        """ファイルが更新されるまで待機

        Args:
            file_path: 監視するファイルパス
            max_age_sec: 許容する最大経過時間
            timeout: タイムアウト秒数
            interval: チェック間隔秒数

        Returns:
            ファイルが更新された場合 True

        Raises:
            TimeoutError: タイムアウトした場合
        """
        import pathlib

        import my_lib.footprint

        path = pathlib.Path(file_path)

        def check() -> bool:
            if not path.exists():
                return False
            elapsed = my_lib.footprint.elapsed(path)
            return elapsed < max_age_sec

        return TimeHelper.wait_until(
            check,
            timeout=timeout,
            interval=interval,
            message=f"File {file_path} was not updated",
        )

    @staticmethod
    def retry(
        func: Callable,
        max_attempts: int = 3,
        delay: float = 1.0,
        exceptions: tuple = (Exception,),
    ) -> object:
        """失敗時にリトライする

        Args:
            func: 実行する関数
            max_attempts: 最大試行回数
            delay: リトライ間隔秒数
            exceptions: リトライする例外の種類

        Returns:
            関数の戻り値

        Raises:
            最後の例外
        """
        last_exception = None
        for attempt in range(max_attempts):
            try:
                return func()
            except exceptions as e:
                last_exception = e
                logging.debug(
                    "Attempt %d/%d failed: %s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
                if attempt < max_attempts - 1:
                    time.sleep(delay)

        raise last_exception  # type: ignore


class SpeedupHelper:
    """時間加速ヘルパー

    テスト実行時の時間を加速する。
    """

    def __init__(self, speedup: int = 100):
        """初期化

        Args:
            speedup: 加速倍率
        """
        self.speedup = speedup
        self.base_time = time.time()
        self.original_time: Callable | None = None

    def apply(self, mocker: MockerFixture) -> None:
        """時間加速を適用

        Args:
            mocker: pytest-mock の mocker fixture
        """
        self.base_time = time.time()
        self.original_time = time.time

        def accelerated_time() -> float:
            real_elapsed = time.time.__wrapped__() - self.base_time  # type: ignore
            return self.base_time + (real_elapsed * self.speedup)

        mocker.patch("time.time", side_effect=accelerated_time)

    def real_sleep(self, seconds: float) -> None:
        """実時間でスリープ (加速の影響を受けない)

        Args:
            seconds: スリープ秒数
        """
        time.sleep(seconds / self.speedup)
