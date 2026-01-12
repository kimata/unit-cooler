#!/usr/bin/env python3
"""
電磁弁を可変デューティ制御します。

Usage:
  valve.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
import threading
import time
from typing import TYPE_CHECKING

import my_lib.footprint
import my_lib.rpi

import unit_cooler.actuator.work_log
import unit_cooler.const

if TYPE_CHECKING:
    from unit_cooler.config import Config

STAT_DIR_PATH = pathlib.Path("/dev/shm")  # noqa: S108

# STATE が WORKING になった際に作られるファイル。Duty 制御している場合、
# OFF Duty から ON Duty に遷移する度に変更日時が更新される。
# STATE が IDLE になった際に削除される。
# (OFF Duty になって実際にバルブを閉じただけでは削除されない)
STAT_PATH_VALVE_STATE_WORKING = STAT_DIR_PATH / "unit_cooler" / "valve" / "state" / "working"

# STATE が IDLE になった際に作られるファイル。
# (OFF Duty になって実際にバルブを閉じただけでは作られない)
# STATE が WORKING になった際に削除される。
STAT_PATH_VALVE_STATE_IDLE = STAT_DIR_PATH / "unit_cooler" / "valve" / "state" / "idle"

# 実際にバルブを開いた際に作られるファイル。
# 実際にバルブを閉じた際に削除される。
STAT_PATH_VALVE_OPEN = STAT_DIR_PATH / "unit_cooler" / "valve" / "open"

# 実際にバルブを閉じた際に作られるファイル。
# 実際にバルブを開いた際に削除される。
STAT_PATH_VALVE_CLOSE = STAT_DIR_PATH / "unit_cooler" / "valve" / "close"

pin_no: int | None = None
valve_lock: threading.Lock | None = None
ctrl_hist: list = []
config: Config | None = None


def init(pin: int, valve_config: Config) -> None:
    global pin_no  # noqa: PLW0603
    global valve_lock  # noqa: PLW0603
    global config  # noqa: PLW0603

    pin_no = pin
    valve_lock = threading.Lock()
    config = valve_config

    my_lib.footprint.clear(STAT_PATH_VALVE_STATE_WORKING)
    my_lib.footprint.update(STAT_PATH_VALVE_STATE_IDLE)

    my_lib.rpi.gpio.setwarnings(False)
    my_lib.rpi.gpio.setmode(my_lib.rpi.gpio.BCM)
    my_lib.rpi.gpio.setup(pin_no, my_lib.rpi.gpio.OUT)

    set_state(unit_cooler.const.VALVE_STATE.CLOSE)


# NOTE: テスト用
def clear_stat():
    global ctrl_hist  # noqa: PLW0603

    my_lib.footprint.clear(STAT_PATH_VALVE_STATE_WORKING)
    my_lib.footprint.clear(STAT_PATH_VALVE_STATE_IDLE)
    my_lib.footprint.clear(STAT_PATH_VALVE_OPEN)
    my_lib.footprint.clear(STAT_PATH_VALVE_CLOSE)
    ctrl_hist = []


# NOTE: テスト用
def get_hist():
    global ctrl_hist

    return ctrl_hist


# NOTE: 実際にバルブを開きます。
# 現在のバルブの状態と、バルブが現在の状態になってからの経過時間を返します。
def set_state(valve_state):
    global pin_no
    global valve_lock
    global ctrl_hist

    with valve_lock:
        curr_state = get_state()

        if valve_state != curr_state:
            logging.info("VALVE: %s -> %s", curr_state.name, valve_state.name)
            # NOTE: テスト時のみ履歴を記録
            import os

            if os.environ.get("TEST") == "true":
                ctrl_hist.append(curr_state)

            # メトリクス記録
            try:
                from unit_cooler.metrics import get_metrics_collector

                global config

                if config is not None:
                    metrics_db_path = config.actuator.metrics.data
                    metrics_collector = get_metrics_collector(metrics_db_path)
                    metrics_collector.record_valve_operation()
            except Exception:
                logging.debug("Failed to record valve operation metrics")

        my_lib.rpi.gpio.output(pin_no, valve_state.value)

        if valve_state == unit_cooler.const.VALVE_STATE.OPEN:
            my_lib.footprint.clear(STAT_PATH_VALVE_CLOSE)
            if not my_lib.footprint.exists(STAT_PATH_VALVE_OPEN):
                my_lib.footprint.update(STAT_PATH_VALVE_OPEN)
        else:
            my_lib.footprint.clear(STAT_PATH_VALVE_OPEN)
            if not my_lib.footprint.exists(STAT_PATH_VALVE_CLOSE):
                my_lib.footprint.update(STAT_PATH_VALVE_CLOSE)

    return get_status()


# NOTE: 実際のバルブの状態を返します
def get_state():
    global pin_no

    if my_lib.rpi.gpio.input(pin_no) == 1:
        return unit_cooler.const.VALVE_STATE.OPEN
    else:
        return unit_cooler.const.VALVE_STATE.CLOSE


# NOTE: 実際のバルブの状態と、その状態になってからの経過時間を返します
def get_status():
    global valve_lock

    with valve_lock:
        valve_state = get_state()

        if valve_state == unit_cooler.const.VALVE_STATE.OPEN:
            assert my_lib.footprint.exists(STAT_PATH_VALVE_OPEN)  # noqa: S101

            return {
                "state": valve_state,
                "duration": my_lib.footprint.elapsed(STAT_PATH_VALVE_OPEN),
            }
        else:  # noqa: PLR5501
            if my_lib.footprint.exists(STAT_PATH_VALVE_CLOSE):
                return {
                    "state": valve_state,
                    "duration": my_lib.footprint.elapsed(STAT_PATH_VALVE_CLOSE),
                }
            else:
                return {"state": valve_state, "duration": 0}


# NOTE: バルブを動作状態にします。
# Duty 制御を実現するため、OFF Duty 期間の場合はバルブを閉じます。
# 実際にバルブを開いてからの経過時間を返します。
# duty_info = { "enable": bool, "on": on_sec, "off": off_sec }
def set_cooling_working(duty_info):
    logging.debug(duty_info)

    my_lib.footprint.clear(STAT_PATH_VALVE_STATE_IDLE)

    if not my_lib.footprint.exists(STAT_PATH_VALVE_STATE_WORKING):
        my_lib.footprint.update(STAT_PATH_VALVE_STATE_WORKING)
        unit_cooler.actuator.work_log.add("冷却を開始します。")
        logging.info("COOLING: IDLE -> WORKING")
        return set_state(unit_cooler.const.VALVE_STATE.OPEN)

    if not duty_info["enable"]:
        # NOTE Duty 制御しない場合
        logging.info("COOLING: WORKING")
        return set_state(unit_cooler.const.VALVE_STATE.OPEN)

    status = get_status()

    if status["state"] == unit_cooler.const.VALVE_STATE.OPEN:
        # NOTE: 現在バルブが開かれている
        if status["duration"] >= duty_info["on_sec"]:
            logging.info("COOLING: WORKING (OFF duty, %d sec left)", duty_info["off_sec"])
            unit_cooler.actuator.work_log.add("OFF Duty になったのでバルブを締めます。")
            return set_state(unit_cooler.const.VALVE_STATE.CLOSE)
        else:
            logging.info("COOLING: WORKING (ON duty, %d sec left)", duty_info["on_sec"] - status["duration"])

            return set_state(unit_cooler.const.VALVE_STATE.OPEN)
    else:  # noqa: PLR5501
        # NOTE: 現在バルブが閉じられている
        if status["duration"] >= duty_info["off_sec"]:
            logging.info("COOLING: WORKING (ON duty, %d sec left)", duty_info["on_sec"])
            unit_cooler.actuator.work_log.add("ON Duty になったのでバルブを開けます。")
            return set_state(unit_cooler.const.VALVE_STATE.OPEN)
        else:
            logging.info(
                "COOLING: WORKING (OFF duty, %d sec left)", duty_info["off_sec"] - status["duration"]
            )
            return set_state(unit_cooler.const.VALVE_STATE.CLOSE)


def set_cooling_idle():
    my_lib.footprint.clear(STAT_PATH_VALVE_STATE_WORKING)

    if not my_lib.footprint.exists(STAT_PATH_VALVE_STATE_IDLE):
        my_lib.footprint.update(STAT_PATH_VALVE_STATE_IDLE)
        unit_cooler.actuator.work_log.add("冷却を停止しました。")
        logging.info("COOLING: WORKING -> IDLE")
        return set_state(unit_cooler.const.VALVE_STATE.CLOSE)
    else:
        logging.info("COOLING: IDLE")
        return set_state(unit_cooler.const.VALVE_STATE.CLOSE)


def set_cooling_state(control_message):
    if control_message["state"] == unit_cooler.const.COOLING_STATE.WORKING:
        return set_cooling_working(control_message["duty"])
    else:
        return set_cooling_idle()


if __name__ == "__main__":
    # TEST Code
    import multiprocessing

    import docopt
    import my_lib.logger
    import my_lib.webapp.config
    import my_lib.webapp.log

    from unit_cooler.config import Config

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)
    event_queue = multiprocessing.Queue()

    my_lib.webapp.config.init(config.actuator.web_server.webapp.to_webapp_config())
    my_lib.webapp.log.init(config.actuator.web_server.webapp.to_webapp_config())
    unit_cooler.actuator.work_log.init(config, event_queue)
    init(config.actuator.control.valve.pin_no, config)

    while True:
        set_cooling_state(
            {
                "state": unit_cooler.const.COOLING_STATE.WORKING,
                "mode_index": 1,
                "duty": {"enable": True, "on_sec": 1, "off_sec": 3},
            }
        )
        time.sleep(1)
