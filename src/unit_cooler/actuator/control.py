#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import my_lib.time

import unit_cooler.actuator.valve
import unit_cooler.actuator.work_log
import unit_cooler.const
import unit_cooler.util
from unit_cooler.metrics import get_metrics_collector

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

HAZARD_NOTIFY_INTERVAL_MIN = 30


def gen_handle(config: Config, message_queue: Queue[Any]) -> dict[str, Any]:
    return {
        "config": config,
        "message_queue": message_queue,
        "receive_time": my_lib.time.now(),
        "receive_count": 0,
    }


def hazard_register(config: Config) -> None:
    my_lib.footprint.update(config.actuator.control.hazard.file)


def hazard_clear(config: Config) -> None:
    my_lib.footprint.clear(config.actuator.control.hazard.file)


def hazard_notify(config: Config, message: str) -> None:
    if my_lib.footprint.elapsed(config.actuator.control.hazard.file) / 60 > HAZARD_NOTIFY_INTERVAL_MIN:
        unit_cooler.actuator.work_log.add(message, unit_cooler.const.LOG_LEVEL.ERROR)

        hazard_register(config)

    unit_cooler.actuator.valve.set_state(unit_cooler.const.VALVE_STATE.CLOSE)


def hazard_check(config: Config) -> bool:
    if my_lib.footprint.exists(config.actuator.control.hazard.file):
        hazard_notify(config, "過去に水漏れもしくは電磁弁の故障が検出されているので制御を停止しています。")
        return True
    else:
        return False


def get_control_message_impl(handle: dict[str, Any], last_message: dict[str, Any]) -> dict[str, Any]:
    if handle["message_queue"].empty():
        elapsed = (my_lib.time.now() - handle["receive_time"]).total_seconds()
        threshold = handle["config"].controller.interval_sec * 3
        if elapsed > threshold:
            unit_cooler.actuator.work_log.add(
                "冷却モードの指示を受信できません。", unit_cooler.const.LOG_LEVEL.ERROR
            )

        return last_message

    control_message = None
    while not handle["message_queue"].empty():
        control_message = handle["message_queue"].get()

        logging.info("Receive: %s", control_message)

        handle["receive_time"] = my_lib.time.now()
        handle["receive_count"] += 1
        if os.environ.get("TEST", "false") == "true":
            # NOTE: テスト時は、コマンドの数を整合させたいので、
            # 1 回に1個のコマンドのみ処理する。
            break

    if control_message["mode_index"] != last_message["mode_index"]:
        unit_cooler.actuator.work_log.add(
            ("冷却モードが変更されました。({before} → {after})").format(
                before="init" if last_message["mode_index"] == -1 else last_message["mode_index"],
                after=control_message["mode_index"],
            )
        )

    return control_message


def get_control_message(handle: dict[str, Any], last_message: dict[str, Any]) -> dict[str, Any]:
    try:
        return get_control_message_impl(handle, last_message)
    except OverflowError:  # pragma: no cover
        # NOTE: テストする際、timemachinefreezer 使って日付をいじるとこの例外が発生する
        logging.exception("Failed to get control message")
        return last_message


def execute(config: Config, control_message: dict[str, Any]) -> None:
    if hazard_check(config):
        control_message = {"mode_index": 0, "state": unit_cooler.const.COOLING_STATE.IDLE}

    # メトリクス収集
    try:
        metrics_db_path = config.actuator.metrics.data
        metrics_collector = get_metrics_collector(metrics_db_path)

        # 冷却モードの記録
        cooling_mode = control_message.get("mode_index", 0)
        metrics_collector.update_cooling_mode(cooling_mode)

        # Duty比の記録（control_messageに含まれている場合）
        if "duty" in control_message:
            duty_info = control_message["duty"]
            if duty_info.get("enable", False):
                on_time = duty_info.get("on_sec", 0)
                total_time = on_time + duty_info.get("off_sec", 0)
                if total_time > 0:
                    metrics_collector.update_duty_ratio(on_time, total_time)
    except Exception:
        logging.exception("Failed to collect metrics data")

    unit_cooler.actuator.valve.set_cooling_state(control_message)
