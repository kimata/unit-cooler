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

import logging
import pathlib

import my_lib.healthz
from my_lib.healthz import HealthzTarget

SCHEMA_CONFIG = "config.schema"


def check_liveness(target_list: list[HealthzTarget], port: int | None = None) -> bool:
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
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    mode = args["-m"]
    port = args["-p"]
    debug_mode = args["-D"]

    my_lib.logger.init("hems.unit_cooler", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file, pathlib.Path(SCHEMA_CONFIG))

    logging.info("Mode: %s", mode)
    if mode == "CTRL":
        conf_list = [["controller"]]
        port = None
    elif mode == "WEB":
        conf_list = [["webui", "subscribe"]]
    else:
        conf_list = [["actuator", "subscribe"], ["actuator", "control"], ["actuator", "monitor"]]
        port = None

    target_list = [
        HealthzTarget(
            name=" - ".join(conf_path),
            liveness_file=my_lib.config.get_path(config, conf_path, ["liveness", "file"]),
            interval=(
                lambda x: x
                if x is not None
                else my_lib.config.get_data(config, ["controller"], ["interval_sec"])
            )(my_lib.config.get_data(config, conf_path, ["interval_sec"])),
        )
        for conf_path in conf_list
    ]

    logging.debug(my_lib.pretty.format(target_list))

    if check_liveness(target_list, port):
        logging.info("OK.")
        sys.exit(0)
    else:
        sys.exit(-1)
