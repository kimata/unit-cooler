#!/usr/bin/env python3
from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import my_lib.footprint
import my_lib.time

import unit_cooler.actuator.override
import unit_cooler.actuator.valve_controller
import unit_cooler.actuator.work_log
import unit_cooler.const
import unit_cooler.util
from unit_cooler.messages import ControlMessage, DutyConfig
from unit_cooler.metrics import get_metrics_collector

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from multiprocessing import Queue

    from unit_cooler.config import Config

HAZARD_NOTIFY_INTERVAL_MIN = 30

# 安全側フォールバック用の制御メッセージ（ハザード・オーバーライド・受信途絶時に使用）
MESSAGE_IDLE = ControlMessage(
    mode_index=0,
    state=unit_cooler.const.COOLING_STATE.IDLE,
    duty=DutyConfig(enable=False, on_sec=0, off_sec=0),
)


@dataclass
class ControlHandle:
    """制御ワーカーのハンドル"""

    config: Config
    message_queue: Queue[ControlMessage]
    receive_time: datetime.datetime = field(default_factory=my_lib.time.now)
    receive_count: int = 0
    # 制御指示の途絶を既に通知したか（途絶中の ERROR ログ・IDLE フォールバックを 1 回に抑える）
    timeout_notified: bool = False
    # 最後に「受信した」メッセージのモード。last_message にはハザード等で差し替えた実効メッセージが
    # 入るため、モード変更ログの判定は受信メッセージ同士で行う（None は未受信）。
    last_receive_mode_index: int | None = None


def gen_handle(config: Config, message_queue: Queue[ControlMessage]) -> ControlHandle:
    return ControlHandle(config=config, message_queue=message_queue, receive_time=my_lib.time.now())


def hazard_register(config: Config) -> None:
    my_lib.footprint.update(config.actuator.control.hazard.file)


def hazard_clear(config: Config) -> None:
    my_lib.footprint.clear(config.actuator.control.hazard.file)


def hazard_notify(config: Config, message: str, suppress_key: str | None = None) -> None:
    """ハザードを通知し、ラッチを登録してバルブを強制閉鎖する

    通知（ERROR ログ・Slack）は work_log の抑制機構で HAZARD_NOTIFY_INTERVAL_MIN 分に
    1 回に抑える。ラッチは初回検知時のみ登録し、初回検知時刻を保持する。

    Args:
        config: 設定
        message: 通知メッセージ
        suppress_key: 通知抑制の判定キー（メッセージに可変値が含まれる場合に指定）
    """
    unit_cooler.actuator.work_log.add(
        message,
        unit_cooler.const.LOG_LEVEL.ERROR,
        suppress_interval_min=HAZARD_NOTIFY_INTERVAL_MIN,
        suppress_key=suppress_key,
    )

    # NOTE: 既にラッチが存在する場合は上書きせず、初回検知時刻を保持する
    if not my_lib.footprint.exists(config.actuator.control.hazard.file):
        hazard_register(config)

    unit_cooler.actuator.valve_controller.get_valve_controller().set_state(
        unit_cooler.const.VALVE_STATE.CLOSE
    )


def hazard_check(config: Config) -> bool:
    if my_lib.footprint.exists(config.actuator.control.hazard.file):
        hazard_notify(config, "過去に水漏れもしくは電磁弁の故障が検出されているので制御を停止しています。")
        return True
    else:
        return False


def get_control_message_impl(handle: ControlHandle, last_message: ControlMessage) -> ControlMessage:
    if handle.message_queue.empty():
        elapsed = (my_lib.time.now() - handle.receive_time).total_seconds()
        threshold = handle.config.controller.interval_sec * 3
        if elapsed > threshold:
            if not handle.timeout_notified:
                unit_cooler.actuator.work_log.add(
                    "冷却モードの指示を受信できません。", unit_cooler.const.LOG_LEVEL.ERROR
                )
                handle.timeout_notified = True

            # NOTE: 安全側のフォールバック。Controller 途絶中に last_message（WORKING かも）の
            # まま散水を続けると、水漏れ等のリスクが残るため IDLE に落として停止する。
            return MESSAGE_IDLE

        return last_message

    control_message: ControlMessage | None = None
    while not handle.message_queue.empty():
        control_message = handle.message_queue.get()

        logger.info("Receive: %s", control_message)

        handle.receive_time = my_lib.time.now()
        handle.receive_count += 1
        handle.timeout_notified = False
        if os.environ.get("TEST", "false") == "true":
            # NOTE: テスト時は、コマンドの数を整合させたいので、
            # 1 回に1個のコマンドのみ処理する。
            break

    # while ループに入った時点でキューは空でないことが保証されているため、
    # ここで control_message は必ず設定されている
    assert control_message is not None  # noqa: S101

    prev_mode_index = (
        handle.last_receive_mode_index
        if handle.last_receive_mode_index is not None
        else last_message.mode_index
    )
    if control_message.mode_index != prev_mode_index:
        unit_cooler.actuator.work_log.add(
            ("冷却モードが変更されました。({before} → {after})").format(
                before="init" if prev_mode_index == -1 else prev_mode_index,
                after=control_message.mode_index,
            )
        )
    handle.last_receive_mode_index = control_message.mode_index

    return control_message


def get_control_message(handle: ControlHandle, last_message: ControlMessage) -> ControlMessage:
    try:
        return get_control_message_impl(handle, last_message)
    except OverflowError:  # pragma: no cover
        # NOTE: テストする際、timemachinefreezer 使って日付をいじるとこの例外が発生する
        logger.exception("Failed to get control message")
        return last_message


def execute(config: Config, control_message: ControlMessage) -> ControlMessage:
    """制御メッセージを実行し、実際に適用した「実効メッセージ」を返す

    ハザード発動中や手動オーバーライド中は IDLE に差し替えたメッセージを適用・返却する。
    呼び出し元は戻り値を last_control_message として保存することで、
    monitor 側の送信・配信に実際の運転状態が反映される。
    """
    if hazard_check(config):
        control_message = MESSAGE_IDLE
    elif unit_cooler.actuator.override.is_active(config):
        # NOTE: 手動オーバーライド中は強制 OFF（失効時刻を過ぎると自動で通常運転に戻る）
        control_message = MESSAGE_IDLE

    # メトリクス収集
    try:
        metrics_db_path = config.actuator.metrics.data
        metrics_collector = get_metrics_collector(metrics_db_path)

        # 冷却モードの記録
        metrics_collector.update_cooling_mode(control_message.mode_index)

        # Duty比の記録
        if control_message.duty.enable:
            on_time = control_message.duty.on_sec
            total_time = on_time + control_message.duty.off_sec
            if total_time > 0:
                metrics_collector.update_duty_ratio(on_time, total_time)
    except Exception:
        logger.exception("Failed to collect metrics data")

    unit_cooler.actuator.valve_controller.get_valve_controller().set_cooling_state(control_message)

    return control_message
