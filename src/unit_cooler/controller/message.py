#!/usr/bin/env python3
"""
アクチュエータに送る制御メッセージの一覧を表示します。

Usage:
  message.py [-D]

Options:
  -D                : デバッグモードで動作します。
"""

import logging
from typing import TypedDict

import unit_cooler.const


class DutyDict(TypedDict):
    enable: bool
    on_sec: int
    off_sec: int


class ControlMessageDict(TypedDict):
    state: unit_cooler.const.COOLING_STATE
    duty: DutyDict


# アクチュエータへの指示に使うメッセージ
CONTROL_MESSAGE_LIST: list[ControlMessageDict] = [
    # 0
    {
        "state": unit_cooler.const.COOLING_STATE.IDLE,
        "duty": {"enable": False, "on_sec": 0 * 60, "off_sec": 0 * 60},
    },
    # 1
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 1 * 60, "off_sec": 14 * 60},
    },
    # 2
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 2 * 60, "off_sec": 13 * 60},
    },
    # 3
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 3 * 60, "off_sec": 12 * 60},
    },
    # 4
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 4 * 60, "off_sec": 11 * 60},
    },
    # 5
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 5 * 60, "off_sec": 10 * 60},
    },
    # 6
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 6 * 60, "off_sec": 9 * 60},
    },
    # 7
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 8 * 60, "off_sec": 7 * 60},
    },
    # 8
    {
        "state": unit_cooler.const.COOLING_STATE.WORKING,
        "duty": {"enable": True, "on_sec": 10 * 60, "off_sec": 5 * 60},
    },
]


def print_control_msg():
    for control_msg in CONTROL_MESSAGE_LIST:
        if control_msg["duty"]["enable"]:
            on_sec = control_msg["duty"]["on_sec"]
            off_sec = int(control_msg["duty"]["off_sec"])
            total = on_sec + off_sec
            on_ratio = 100.0 * on_sec / total if total != 0 else 0

            logging.info(
                "state: %s, on_se_sec: %s sec, off_sec: %s sec, on_ratio: %.1f%%",
                control_msg["state"].name,
                f"{on_sec:,}",
                f"{off_sec:,}",
                on_ratio,
            )
        else:
            logging.info("state: %s", control_msg["state"].name)


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    print_control_msg()
