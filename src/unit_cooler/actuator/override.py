#!/usr/bin/env python3
"""
手動オーバーライド（強制 OFF）の状態管理を提供します。

WebUI からの指示で一定時間だけ散水を強制停止するための状態を管理します。
状態は再起動を跨いで保持するため、state_file 経由で永続化します。
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import my_lib.time

import unit_cooler.actuator.state_file

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib

    from unit_cooler.config import Config

OVERRIDE_FILE_NAME = "unit_cooler.override.json"

# オーバーライド期間〔分〕の下限・上限
DURATION_MIN_LOWER = 1
DURATION_MIN_UPPER = 1440


@dataclass(frozen=True)
class OverrideState:
    """手動オーバーライド状態（ファイル永続化用）"""

    # オーバーライドの失効時刻
    until: datetime.datetime

    def to_dict(self) -> dict[str, Any]:
        return {"until": self.until.isoformat()}

    @classmethod
    def parse(cls, data: dict[str, Any]) -> OverrideState:
        until = datetime.datetime.fromisoformat(data["until"])
        # NOTE: naive datetime は現在時刻（aware）と比較できないので、破損扱いにする
        if until.tzinfo is None:
            raise ValueError(f"until must be timezone-aware: {data['until']}")
        return cls(until=until)


def get_file_path(config: Config) -> pathlib.Path:
    """オーバーライド状態の永続化ファイルのパスを返す"""
    return unit_cooler.actuator.state_file.get_path(config, OVERRIDE_FILE_NAME)


def set_override(config: Config, duration_min: int) -> OverrideState:
    """オーバーライドを設定する（duration_min 分後まで強制 OFF）"""
    if not (DURATION_MIN_LOWER <= duration_min <= DURATION_MIN_UPPER):
        raise ValueError(
            f"duration_min must be between {DURATION_MIN_LOWER} and {DURATION_MIN_UPPER}: {duration_min}"
        )

    state = OverrideState(until=my_lib.time.now() + datetime.timedelta(minutes=duration_min))

    unit_cooler.actuator.state_file.save(get_file_path(config), state.to_dict())

    logger.info("Manual override set until %s", state.until.isoformat())

    return state


def clear_override(config: Config) -> None:
    """オーバーライドを解除する"""
    get_file_path(config).unlink(missing_ok=True)


def get_override(config: Config) -> OverrideState | None:
    """有効なオーバーライド状態を返す（未設定・失効時は None）

    失効している場合は永続化ファイルを削除して自動的に通常運転へ戻す。
    """
    state = unit_cooler.actuator.state_file.load(get_file_path(config), OverrideState.parse)
    if state is None:
        return None

    if state.until <= my_lib.time.now():
        logger.info("Manual override expired, back to normal operation")
        clear_override(config)
        return None

    return state


def is_active(config: Config) -> bool:
    """オーバーライドが有効かどうかを返す"""
    return get_override(config) is not None
