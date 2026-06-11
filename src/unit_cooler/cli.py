#!/usr/bin/env python3
"""エントリポイント共通処理

docopt 解析、ロガー初期化、Config 読み込みをまとめて行う。
"""

from __future__ import annotations

import logging
import pathlib

import docopt
import my_lib.logger

from unit_cooler.config import Config

SCHEMA_CONFIG = "schema/config.schema"


def init(doc: str, name: str = "hems.unit_cooler") -> tuple[dict, Config]:
    """docopt 解析 + ロガー初期化 + Config 読み込み

    Args:
        doc: docopt 用の Usage 文字列（モジュールの __doc__）
        name: ロガー名

    Returns:
        (docopt 解析結果, Config)
    """
    args = docopt.docopt(doc)

    my_lib.logger.init(name, level=logging.DEBUG if args.get("-D") else logging.INFO)

    config = Config.load(args["-c"], pathlib.Path(SCHEMA_CONFIG))

    return args, config
