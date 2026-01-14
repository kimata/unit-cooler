#!/usr/bin/env python3
"""
屋外の気象情報とエアコンの稼働状況に基づき、冷却モードを決定します。

Usage:
  engine.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import dataclasses
import logging
from typing import Any

import unit_cooler.controller.message
import unit_cooler.controller.sensor
import unit_cooler.util
from unit_cooler.config import Config
from unit_cooler.messages import ControlMessage, DutyConfig, StatusInfo

# 最低でもこの時間は ON にする (テスト時含む)
ON_SEC_MIN = 5
# 最低でもこの時間は OFF にする (テスト時含む)
OFF_SEC_MIN = 5

# dummy_cooling_mode の状態をモジュールレベル変数で管理
_dummy_prev_mode: int = 0


def dummy_cooling_mode():
    global _dummy_prev_mode
    import random

    current_mode = _dummy_prev_mode
    max_mode = len(unit_cooler.controller.message.CONTROL_MESSAGE_LIST) - 1

    # 60%の確率で現状維持、40%の確率で変更
    if random.random() < 0.6:  # noqa: S311
        cooling_mode = current_mode
    elif current_mode == 1:
        # モード1の場合、特別な処理
        if random.random() < 0.1:  # noqa: S311  # 10%の確率で0へ
            cooling_mode = 0
        elif random.random() < 0.5:  # noqa: S311  # 残り90%のうち50%で+1
            cooling_mode = min(current_mode + 1, max_mode)
        else:  # 残り90%のうち50%で現状維持
            cooling_mode = current_mode
    elif current_mode == 0:
        # モード0の場合、+1のみ
        cooling_mode = 1
    elif current_mode == max_mode:
        # 最大モードの場合、-1のみ
        cooling_mode = current_mode - 1
    else:
        # その他の場合、50%で+1、50%で-1
        cooling_mode = current_mode + 1 if random.random() < 0.5 else current_mode - 1  # noqa: S311

    _dummy_prev_mode = cooling_mode

    logging.info("cooling_mode: %d (prev: %d)", cooling_mode, current_mode)

    return {"cooling_mode": cooling_mode}


def set_dummy_prev_mode(mode: int) -> None:
    """テスト用: dummy_cooling_mode の prev_mode を設定します。"""
    global _dummy_prev_mode
    _dummy_prev_mode = mode


def get_dummy_prev_mode() -> int:
    """テスト用: dummy_cooling_mode の prev_mode を取得します。"""
    return _dummy_prev_mode


def judge_cooling_mode(config: Config, sense_data: dict[str, Any]) -> dict[str, Any]:
    logging.info("Judge cooling mode")

    # 閾値を config から取得
    thresholds = dataclasses.asdict(config.controller.decision.thresholds)

    try:
        cooler_activity = unit_cooler.controller.sensor.get_cooler_activity(sense_data, thresholds)
    except RuntimeError as e:
        unit_cooler.util.notify_error(config, e.args[0])
        cooler_activity = {"status": 0, "message": None}

    if cooler_activity["status"] == 0:
        outdoor_status = {"status": None, "message": None}
        cooling_mode = 0
    else:
        outdoor_status = unit_cooler.controller.sensor.get_outdoor_status(sense_data, thresholds)
        cooling_mode = max(cooler_activity["status"] + outdoor_status["status"], 0)

    if cooler_activity["message"] is not None:
        logging.info(cooler_activity["message"])
    if outdoor_status["message"] is not None:
        logging.info(outdoor_status["message"])

    logging.info(
        "cooling_mode: %d (cooler_status: %s, outdoor_status: %s)",
        cooling_mode,
        cooler_activity["status"],
        outdoor_status["status"],
    )

    return {
        "cooling_mode": cooling_mode,
        "cooler_status": cooler_activity,
        "outdoor_status": outdoor_status,
        "sense_data": sense_data,
    }


def gen_control_msg(config: Config, dummy_mode: bool = False, speedup: int = 1) -> dict[str, Any]:
    if dummy_mode:
        sense_data = {}
        mode = dummy_cooling_mode()
        # ダミーモード用のデフォルト値
        cooler_status = StatusInfo(status=0, message=None)
        outdoor_status = StatusInfo(status=0, message=None)
    else:
        sense_data = unit_cooler.controller.sensor.get_sense_data(config)
        mode = judge_cooling_mode(config, sense_data)
        # judge_cooling_mode から取得した値を StatusInfo に変換
        cooler_status = StatusInfo(
            status=mode["cooler_status"]["status"],
            message=mode["cooler_status"]["message"],
        )
        outdoor_status = StatusInfo(
            status=mode["outdoor_status"]["status"],
            message=mode["outdoor_status"]["message"],
        )

    mode_index = min(mode["cooling_mode"], len(unit_cooler.controller.message.CONTROL_MESSAGE_LIST) - 1)

    # 既存のメッセージリストから基本設定を取得
    base_msg = unit_cooler.controller.message.CONTROL_MESSAGE_LIST[mode_index]
    base_duty = base_msg["duty"]

    # DutyConfig を構築（speedup 対応）
    if dummy_mode:
        duty = DutyConfig(
            enable=base_duty["enable"],
            on_sec=int(max(base_duty["on_sec"] / speedup, ON_SEC_MIN)),
            off_sec=int(max(base_duty["off_sec"] / speedup, OFF_SEC_MIN)),
        )
    else:
        duty = DutyConfig(
            enable=base_duty["enable"],
            on_sec=base_duty["on_sec"],
            off_sec=base_duty["off_sec"],
        )

    # ControlMessage を構築
    control_msg = ControlMessage(
        state=base_msg["state"],
        duty=duty,
        mode_index=mode_index,
        sense_data=sense_data,
        cooler_status=cooler_status,
        outdoor_status=outdoor_status,
    )

    logging.info(control_msg.to_dict())

    # 後方互換性のため dict で返す
    return control_msg.to_dict()


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.logger
    import my_lib.pretty

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)

    logging.info(my_lib.pretty.format(gen_control_msg(config)))
