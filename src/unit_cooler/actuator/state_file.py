#!/usr/bin/env python3
"""
WebUI から設定される状態（手動オーバーライド・稼働期間）の永続化を提供します。

状態は再起動を跨いで保持するため、ハザードファイルと同じディレクトリ（永続領域）の
JSON ファイルに保存します。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, TypeVar

import my_lib.pytest_util

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from unit_cooler.config import Config

T = TypeVar("T")


def get_path(config: Config, file_name: str) -> pathlib.Path:
    """状態ファイルのパスを返す（ハザードファイルと同じディレクトリ）

    my_lib.footprint と同様、pytest-xdist 並列実行時はワーカー固有のパスを返す。
    """
    return my_lib.pytest_util.get_path(config.actuator.control.hazard.file.parent / file_name)


def load(path: pathlib.Path, parse: Callable[[dict[str, Any]], T]) -> T | None:
    """状態ファイルを読み込んで parse した結果を返す（不在・破損時は None）"""
    if not path.exists():
        return None

    try:
        return parse(json.loads(path.read_text()))
    except (ValueError, KeyError, TypeError, OSError):
        logger.warning("State file is broken, ignoring: %s", path)
        return None


def save(path: pathlib.Path, data: dict[str, Any]) -> None:
    """状態ファイルを書き込む

    書き込み途中の電源断で破損したファイルが残らないよう、一時ファイルに書いてから
    置き換える。
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data))
    tmp_path.replace(path)
