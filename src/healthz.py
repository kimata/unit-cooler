#!/usr/bin/env python3
"""
Liveness のチェックを行います

Usage:
  healthz.py [-c CONFIG] [-m MODE] [-p PORT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -m (CRTL|ACT|WEB) : 動作モード [default: CTRL]
  -p PORT           : WEB サーバのポートを指定します。[default: 5000]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
from typing import TYPE_CHECKING

import my_lib.healthz

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unit_cooler.config import Config

SCHEMA_CONFIG = "schema/config.schema"


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
    else:  # ACT
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


def check_liveness(target_list: list[my_lib.healthz.HealthzTarget], port: int | None = None) -> bool:
    failed = my_lib.healthz.check_liveness_all(target_list)
    if failed:
        return False

    if port is not None:
        return my_lib.healthz.check_http_port(port)
    else:
        return True


if __name__ == "__main__":
    import sys

    import docopt
    import my_lib.logger
    import my_lib.pretty

    from unit_cooler.config import Config

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    mode = args["-m"]
    port = args["-p"]
    debug_mode = args["-D"]

    my_lib.logger.init("hems.unit_cooler", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file, pathlib.Path(SCHEMA_CONFIG))

    logger.info("Mode: %s", mode)
    if mode == "CTRL" or mode == "ACT":
        port = None

    target_list = get_liveness_targets(config, mode)

    logger.debug(my_lib.pretty.format(target_list))

    if check_liveness(target_list, port):
        logger.info("OK.")
        sys.exit(0)
    else:
        sys.exit(-1)
