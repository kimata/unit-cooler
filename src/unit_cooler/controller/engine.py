#!/usr/bin/env python3
"""
屋外の気象情報とエアコンの稼働状況に基づき、冷却モードを決定します。

Usage:
  engine.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import copy
import logging

import my_lib.notify.slack

import unit_cooler.controller.message
import unit_cooler.controller.sensor
import unit_cooler.util

# 最低でもこの時間は ON にする (テスト時含む)
ON_SEC_MIN = 5
# 最低でもこの時間は OFF にする (テスト時含む)
OFF_SEC_MIN = 5


def dummy_cooling_mode():
    import random

    current_mode = dummy_cooling_mode.prev_mode
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

    dummy_cooling_mode.prev_mode = cooling_mode

    logging.info("cooling_mode: %d (prev: %d)", cooling_mode, current_mode)

    return {"cooling_mode": cooling_mode}


dummy_cooling_mode.prev_mode = 0


def judge_cooling_mode(config, sense_data):
    logging.info("Judge cooling mode")

    try:
        cooler_activity = unit_cooler.controller.sensor.get_cooler_activity(sense_data)
    except RuntimeError as e:
        unit_cooler.util.notify_error(config, e.args[0])
        cooler_activity = {"status": 0, "message": None}

    if cooler_activity["status"] == 0:
        outdoor_status = {"status": None, "message": None}
        cooling_mode = 0
    else:
        outdoor_status = unit_cooler.controller.sensor.get_outdoor_status(sense_data)
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


def gen_control_msg(config, dummy_mode=False, speedup=1):
    if dummy_mode:
        sense_data = {}
        mode = dummy_cooling_mode()
    else:
        sense_data = unit_cooler.controller.sensor.get_sense_data(config)
        mode = judge_cooling_mode(config, sense_data)

    mode_index = min(mode["cooling_mode"], len(unit_cooler.controller.message.CONTROL_MESSAGE_LIST) - 1)

    control_msg = copy.deepcopy(unit_cooler.controller.message.CONTROL_MESSAGE_LIST[mode_index])

    # NOTE: 参考として、どのモードかも通知する
    control_msg["mode_index"] = mode_index
    # NOTE: メトリクス用に、センサーデータも送る
    control_msg["sense_data"] = sense_data

    if dummy_mode:
        control_msg["duty"]["on_sec"] = max(control_msg["duty"]["on_sec"] / speedup, ON_SEC_MIN)
        control_msg["duty"]["off_sec"] = max(control_msg["duty"]["off_sec"] / speedup, OFF_SEC_MIN)

    logging.info(control_msg)

    return control_msg


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)

    logging.info(my_lib.pretty.format(gen_control_msg(config)))
