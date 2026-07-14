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

import pathlib
from typing import TYPE_CHECKING

import my_lib.healthz
import my_lib.healthz.cli

if TYPE_CHECKING:
    from unit_cooler.config import Config

VALID_MODES = ("CTRL", "ACT", "WEB")
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


def _load_config(config_file, args):
    from unit_cooler.config import Config

    return Config.load(config_file, pathlib.Path(SCHEMA_CONFIG))


def _targets(config, args):
    return get_liveness_targets(config, args["-m"])


SPEC = my_lib.healthz.cli.HealthzCliSpec(
    logger_name="hems.unit_cooler",
    config_loader=_load_config,
    targets_builder=_targets,
    use_http_port=True,
    # CTRL / ACT は WEB サーバを持たないためポートチェックしない
    http_port_enabled=lambda config, args: args["-m"] == "WEB",
)

if __name__ == "__main__":
    assert __doc__ is not None  # noqa: S101
    my_lib.healthz.cli.run(SPEC, __doc__)
