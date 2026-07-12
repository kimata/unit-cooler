#!/usr/bin/env python3
"""
Liveness のチェックを行います

Usage:
  healthz.py [-c CONFIG] [-m MODE] [-p PORT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -m (CTRL|ACT|WEB) : 動作モード [default: CTRL]
  -p PORT           : WEB サーバのポートを指定します。[default: 5000]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import my_lib.healthz

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config

VALID_MODES = ("CTRL", "ACT", "WEB")


def get_liveness_targets(config: Config, mode: str) -> list[my_lib.healthz.HealthzTarget]:
    """モードに応じた Liveness チェック対象を取得する

    Args:
        config: アプリケーション設定
        mode: 動作モード（CTRL, WEB, ACT）

    Returns:
        HealthzTarget のリスト
    """
    # コントローラーのデフォルト interval を取得
    default_interval = config.controller.interval_sec

    if mode == "CTRL":
        return [
            my_lib.healthz.HealthzTarget(
                name="controller",
                liveness_file=config.controller.liveness.file,
                interval=config.controller.interval_sec,
            )
        ]
    elif mode == "WEB":
        return [
            my_lib.healthz.HealthzTarget(
                name="webui - subscribe",
                liveness_file=config.webui.subscribe.liveness.file,
                interval=default_interval,
            )
        ]
    elif mode == "ACT":
        return [
            my_lib.healthz.HealthzTarget(
                name="actuator - subscribe",
                liveness_file=config.actuator.subscribe.liveness.file,
                interval=default_interval,
            ),
            my_lib.healthz.HealthzTarget(
                name="actuator - control",
                liveness_file=config.actuator.control.liveness.file,
                interval=config.actuator.control.interval_sec,
            ),
            my_lib.healthz.HealthzTarget(
                name="actuator - monitor",
                liveness_file=config.actuator.monitor.liveness.file,
                interval=config.actuator.monitor.interval_sec,
            ),
        ]
    else:
        # NOTE: 暗黙に ACT 扱いすると typo に気付けないため、未知モードは明示エラーにする
        raise ValueError(f"Unknown mode: {mode} (expected one of {VALID_MODES})")


if __name__ == "__main__":
    import sys

    import my_lib.pretty

    import unit_cooler.cli

    assert __doc__ is not None  # noqa: S101
    args, config = unit_cooler.cli.init(__doc__)

    mode = args["-m"]
    port = args["-p"]

    logger.info("Mode: %s", mode)
    if mode not in VALID_MODES:
        logger.error("Unknown mode: %s (expected one of %s)", mode, ", ".join(VALID_MODES))
        sys.exit(1)

    if mode == "CTRL" or mode == "ACT":
        port = None

    target_list = get_liveness_targets(config, mode)

    logger.debug(my_lib.pretty.format(target_list))

    failed_targets = my_lib.healthz.check_liveness_all_with_ports(
        target_list,
        http_port=port,
    )

    if not failed_targets:
        logger.info("OK.")
        sys.exit(0)
    else:
        sys.exit(-1)
