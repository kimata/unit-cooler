#!/usr/bin/env python3
"""
稼働期間（散水を行う季節）の設定管理を提供します。

冬季など散水させたくない期間を除外するため、WebUI から「開始月日〜終了月日」を
指定します。年は持たず、毎年同じ期間が適用されます。期間外は Actuator が
散水を強制停止します。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

import my_lib.time

import unit_cooler.actuator.state_file

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import datetime
    import pathlib

    from unit_cooler.config import Config

SEASON_FILE_NAME = "unit_cooler.season.json"

# 各月の最大日数（年を持たないため、2 月は閏年の 29 日まで許容する）
DAYS_IN_MONTH: tuple[int, ...] = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _require_int(value: Any, name: str) -> int:
    # NOTE: bool は int のサブクラスなので明示的に除外する
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer: {value!r}")
    return value


@dataclass(frozen=True, order=True)
class MonthDay:
    """年を持たない月日（比較は月 → 日の順）"""

    month: int
    day: int

    def __post_init__(self) -> None:
        if not (1 <= self.month <= 12):
            raise ValueError(f"month must be between 1 and 12: {self.month}")
        if not (1 <= self.day <= DAYS_IN_MONTH[self.month - 1]):
            raise ValueError(
                f"day must be between 1 and {DAYS_IN_MONTH[self.month - 1]} "
                f"for month {self.month}: {self.day}"
            )

    def to_dict(self) -> dict[str, int]:
        return {"month": self.month, "day": self.day}

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        return cls(month=_require_int(data["month"], "month"), day=_require_int(data["day"], "day"))


@dataclass(frozen=True)
class SeasonSetting:
    """稼働期間の設定

    開始日・終了日はどちらも期間に含む。開始 > 終了 の場合は年をまたぐ期間
    （例: 11月1日〜3月31日）として扱う。
    """

    # False の場合は期間を限定しない（通年稼働）
    enabled: bool
    start: MonthDay
    end: MonthDay

    @classmethod
    def default(cls) -> Self:
        """未設定時の値（通年稼働）"""
        return cls(enabled=False, start=MonthDay(1, 1), end=MonthDay(12, 31))

    def contains(self, date: datetime.date) -> bool:
        """指定日が稼働期間内かどうかを返す"""
        if not self.enabled:
            return True

        # NOTE: 月日のみで比較するため、2月29日を境界にしても平年で破綻しない
        # （開始なら 3月1日から、終了なら 2月28日までとして振る舞う）
        today = MonthDay(date.month, date.day)

        if self.start <= self.end:
            return self.start <= today <= self.end

        # 年をまたぐ場合
        return today >= self.start or today <= self.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }

    @classmethod
    def parse(cls, data: dict[str, Any]) -> Self:
        enabled = data["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean: {enabled!r}")

        return cls(
            enabled=enabled,
            start=MonthDay.parse(data["start"]),
            end=MonthDay.parse(data["end"]),
        )


def get_file_path(config: Config) -> pathlib.Path:
    """稼働期間設定の永続化ファイルのパスを返す"""
    return unit_cooler.actuator.state_file.get_path(config, SEASON_FILE_NAME)


def set_setting(config: Config, setting: SeasonSetting) -> None:
    """稼働期間を設定する"""
    unit_cooler.actuator.state_file.save(get_file_path(config), setting.to_dict())

    logger.info("Operating season set: %s", setting)


def get_setting(config: Config) -> SeasonSetting:
    """稼働期間の設定を返す（未設定・破損時は通年稼働）"""
    setting = unit_cooler.actuator.state_file.load(get_file_path(config), SeasonSetting.parse)

    return setting if setting is not None else SeasonSetting.default()


def is_in_season(config: Config) -> bool:
    """現在が稼働期間内かどうかを返す"""
    return get_setting(config).contains(my_lib.time.now().date())
