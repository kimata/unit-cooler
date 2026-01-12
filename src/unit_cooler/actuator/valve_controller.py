#!/usr/bin/env python3
"""
電磁弁を制御するクラス

電磁弁の状態管理とデューティサイクル制御を担当します。
"""

from __future__ import annotations

import logging
import os
import pathlib
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import my_lib.rpi

import unit_cooler.actuator.work_log
import unit_cooler.const
from unit_cooler.messages import DutyConfig, ValveStatus

if TYPE_CHECKING:
    from unit_cooler.config import Config

STAT_DIR_PATH = pathlib.Path("/dev/shm")  # noqa: S108

# STATE が WORKING になった際に作られるファイル
STAT_PATH_VALVE_STATE_WORKING = STAT_DIR_PATH / "unit_cooler" / "valve" / "state" / "working"
# STATE が IDLE になった際に作られるファイル
STAT_PATH_VALVE_STATE_IDLE = STAT_DIR_PATH / "unit_cooler" / "valve" / "state" / "idle"
# 実際にバルブを開いた際に作られるファイル
STAT_PATH_VALVE_OPEN = STAT_DIR_PATH / "unit_cooler" / "valve" / "open"
# 実際にバルブを閉じた際に作られるファイル
STAT_PATH_VALVE_CLOSE = STAT_DIR_PATH / "unit_cooler" / "valve" / "close"


@dataclass
class ValveController:
    """電磁弁制御クラス"""

    config: Config
    pin_no: int

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _operation_count: int = field(default=0, init=False)
    _ctrl_hist: list[unit_cooler.const.VALVE_STATE] = field(default_factory=list, init=False, repr=False)
    _initialized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """初期化処理"""
        my_lib.footprint.clear(STAT_PATH_VALVE_STATE_WORKING)
        my_lib.footprint.update(STAT_PATH_VALVE_STATE_IDLE)

        my_lib.rpi.gpio.setwarnings(False)
        my_lib.rpi.gpio.setmode(my_lib.rpi.gpio.BCM)
        my_lib.rpi.gpio.setup(self.pin_no, my_lib.rpi.gpio.OUT)

        self.set_state(unit_cooler.const.VALVE_STATE.CLOSE)
        self._initialized = True

    def get_state(self) -> unit_cooler.const.VALVE_STATE:
        """現在のバルブ状態を取得"""
        if my_lib.rpi.gpio.input(self.pin_no) == 1:
            return unit_cooler.const.VALVE_STATE.OPEN
        else:
            return unit_cooler.const.VALVE_STATE.CLOSE

    def set_state(self, valve_state: unit_cooler.const.VALVE_STATE) -> ValveStatus:
        """バルブ状態を設定"""
        with self._lock:
            curr_state = self.get_state()

            if valve_state != curr_state:
                logging.info("VALVE: %s -> %s", curr_state.name, valve_state.name)
                self._operation_count += 1

                # テスト時のみ履歴を記録
                if os.environ.get("TEST") == "true":
                    self._ctrl_hist.append(curr_state)

                # メトリクス記録
                self._record_metrics()

            my_lib.rpi.gpio.output(self.pin_no, valve_state.value)

            if valve_state == unit_cooler.const.VALVE_STATE.OPEN:
                my_lib.footprint.clear(STAT_PATH_VALVE_CLOSE)
                if not my_lib.footprint.exists(STAT_PATH_VALVE_OPEN):
                    my_lib.footprint.update(STAT_PATH_VALVE_OPEN)
            else:
                my_lib.footprint.clear(STAT_PATH_VALVE_OPEN)
                if not my_lib.footprint.exists(STAT_PATH_VALVE_CLOSE):
                    my_lib.footprint.update(STAT_PATH_VALVE_CLOSE)

        return self.get_status()

    def get_status(self) -> ValveStatus:
        """バルブ状態と経過時間を取得"""
        with self._lock:
            valve_state = self.get_state()

            if valve_state == unit_cooler.const.VALVE_STATE.OPEN:
                assert my_lib.footprint.exists(STAT_PATH_VALVE_OPEN)  # noqa: S101
                duration = my_lib.footprint.elapsed(STAT_PATH_VALVE_OPEN)
            elif my_lib.footprint.exists(STAT_PATH_VALVE_CLOSE):
                duration = my_lib.footprint.elapsed(STAT_PATH_VALVE_CLOSE)
            else:
                duration = 0

            return ValveStatus(state=valve_state, duration_sec=duration)

    def get_status_dict(self) -> dict[str, Any]:
        """バルブ状態を dict で取得（後方互換性のため）"""
        status = self.get_status()
        return {
            "state": status.state,
            "duration": status.duration_sec,
        }

    def set_cooling_working(self, duty: DutyConfig | dict[str, Any]) -> ValveStatus:
        """バルブを動作状態に設定（デューティサイクル制御）"""
        # dict の場合は DutyConfig に変換
        duty_config: DutyConfig
        if isinstance(duty, dict):
            duty_config = DutyConfig(
                enable=duty["enable"],
                on_sec=duty["on_sec"],
                off_sec=duty["off_sec"],
            )
        else:
            duty_config = duty

        logging.debug("set_cooling_working: %s", duty_config)

        my_lib.footprint.clear(STAT_PATH_VALVE_STATE_IDLE)

        if not my_lib.footprint.exists(STAT_PATH_VALVE_STATE_WORKING):
            my_lib.footprint.update(STAT_PATH_VALVE_STATE_WORKING)
            unit_cooler.actuator.work_log.add("冷却を開始します。")
            logging.info("COOLING: IDLE -> WORKING")
            return self.set_state(unit_cooler.const.VALVE_STATE.OPEN)

        if not duty_config.enable:
            # Duty 制御しない場合
            logging.info("COOLING: WORKING")
            return self.set_state(unit_cooler.const.VALVE_STATE.OPEN)

        status = self.get_status()

        if status.state == unit_cooler.const.VALVE_STATE.OPEN:
            # 現在バルブが開かれている
            if status.duration_sec >= duty_config.on_sec:
                logging.info("COOLING: WORKING (OFF duty, %d sec left)", duty_config.off_sec)
                unit_cooler.actuator.work_log.add("OFF Duty になったのでバルブを締めます。")
                return self.set_state(unit_cooler.const.VALVE_STATE.CLOSE)
            else:
                logging.info(
                    "COOLING: WORKING (ON duty, %d sec left)", duty_config.on_sec - status.duration_sec
                )
                return self.set_state(unit_cooler.const.VALVE_STATE.OPEN)
        else:
            # 現在バルブが閉じられている
            if status.duration_sec >= duty_config.off_sec:
                logging.info("COOLING: WORKING (ON duty, %d sec left)", duty_config.on_sec)
                unit_cooler.actuator.work_log.add("ON Duty になったのでバルブを開けます。")
                return self.set_state(unit_cooler.const.VALVE_STATE.OPEN)
            else:
                logging.info(
                    "COOLING: WORKING (OFF duty, %d sec left)", duty_config.off_sec - status.duration_sec
                )
                return self.set_state(unit_cooler.const.VALVE_STATE.CLOSE)

    def set_cooling_idle(self) -> ValveStatus:
        """バルブをアイドル状態に設定"""
        my_lib.footprint.clear(STAT_PATH_VALVE_STATE_WORKING)

        if not my_lib.footprint.exists(STAT_PATH_VALVE_STATE_IDLE):
            my_lib.footprint.update(STAT_PATH_VALVE_STATE_IDLE)
            unit_cooler.actuator.work_log.add("冷却を停止しました。")
            logging.info("COOLING: WORKING -> IDLE")
            return self.set_state(unit_cooler.const.VALVE_STATE.CLOSE)
        else:
            logging.info("COOLING: IDLE")
            return self.set_state(unit_cooler.const.VALVE_STATE.CLOSE)

    def set_cooling_state(self, control_message: dict[str, Any]) -> ValveStatus:
        """制御メッセージに基づいてバルブ状態を設定"""
        if control_message["state"] == unit_cooler.const.COOLING_STATE.WORKING:
            return self.set_cooling_working(control_message["duty"])
        else:
            return self.set_cooling_idle()

    def close(self) -> None:
        """クリーンアップ処理"""
        self.set_state(unit_cooler.const.VALVE_STATE.CLOSE)

    def clear_stat(self) -> None:
        """テスト用: 状態をクリア"""
        my_lib.footprint.clear(STAT_PATH_VALVE_STATE_WORKING)
        my_lib.footprint.clear(STAT_PATH_VALVE_STATE_IDLE)
        my_lib.footprint.clear(STAT_PATH_VALVE_OPEN)
        my_lib.footprint.clear(STAT_PATH_VALVE_CLOSE)
        self._ctrl_hist = []

    def get_hist(self) -> list[unit_cooler.const.VALVE_STATE]:
        """テスト用: 操作履歴を取得"""
        return self._ctrl_hist

    @property
    def operation_count(self) -> int:
        """バルブ操作回数を取得"""
        return self._operation_count

    def _record_metrics(self) -> None:
        """メトリクスを記録"""
        try:
            from unit_cooler.metrics import get_metrics_collector

            metrics_db_path = self.config.actuator.metrics.data
            metrics_collector = get_metrics_collector(metrics_db_path)
            metrics_collector.record_valve_operation()
        except Exception:
            logging.debug("Failed to record valve operation metrics")
