#!/usr/bin/env python3
"""
アクチュエータに送る制御メッセージの一覧を表示します。

Usage:
  message.py [-D]

Options:
  -D                : デバッグモードで動作します。
"""

import logging
from dataclasses import dataclass

import unit_cooler.const
from unit_cooler.messages import DutyConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ControlMessageTemplate:
    """制御メッセージのテンプレート"""

    state: unit_cooler.const.COOLING_STATE
    duty: DutyConfig


# アクチュエータへの指示に使うメッセージ
CONTROL_MESSAGE_LIST: list[ControlMessageTemplate] = [
    # 0
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.IDLE,
        duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
    ),
    # 1
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=1 * 60, off_sec=14 * 60),
    ),
    # 2
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=2 * 60, off_sec=13 * 60),
    ),
    # 3
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=3 * 60, off_sec=12 * 60),
    ),
    # 4
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=4 * 60, off_sec=11 * 60),
    ),
    # 5
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=5 * 60, off_sec=10 * 60),
    ),
    # 6
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=6 * 60, off_sec=9 * 60),
    ),
    # 7
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=8 * 60, off_sec=7 * 60),
    ),
    # 8
    ControlMessageTemplate(
        state=unit_cooler.const.COOLING_STATE.WORKING,
        duty=DutyConfig(enable=True, on_sec=10 * 60, off_sec=5 * 60),
    ),
]


def print_control_msg() -> None:
    for control_msg in CONTROL_MESSAGE_LIST:
        if control_msg.duty.enable:
            on_sec = control_msg.duty.on_sec
            off_sec = control_msg.duty.off_sec
            total = on_sec + off_sec
            on_ratio = 100.0 * on_sec / total if total != 0 else 0

            logger.info(
                "state: %s, on_se_sec: %s sec, off_sec: %s sec, on_ratio: %.1f%%",
                control_msg.state.name,
                f"{on_sec:,}",
                f"{off_sec:,}",
                on_ratio,
            )
        else:
            logger.info("state: %s", control_msg.state.name)
