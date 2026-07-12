#!/usr/bin/env python3
"""
屋外の気象情報とエアコンの稼働状況に基づき、冷却モードを決定します。

Usage:
  engine.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import datetime
import logging

import my_lib.time

import unit_cooler.controller.message
import unit_cooler.controller.sensor
import unit_cooler.util
from unit_cooler.config import Config, NightStopConfig
from unit_cooler.messages import ControlMessage, CoolingModeResult, DutyConfig, SenseData, StatusInfo

logger = logging.getLogger(__name__)

# 最低でもこの時間は ON にする (テスト時含む)
ON_SEC_MIN = 5
# 最低でもこの時間は OFF にする (テスト時含む)
OFF_SEC_MIN = 5

# dummy_cooling_mode の状態をモジュールレベル変数で管理
_dummy_prev_mode: int = 0


def dummy_cooling_mode() -> int:
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

    logger.info("cooling_mode: %d (prev: %d)", cooling_mode, current_mode)

    return cooling_mode


def set_dummy_prev_mode(mode: int) -> None:
    """テスト用: dummy_cooling_mode の prev_mode を設定します。"""
    global _dummy_prev_mode
    _dummy_prev_mode = mode


def get_dummy_prev_mode() -> int:
    """テスト用: dummy_cooling_mode の prev_mode を取得します。"""
    return _dummy_prev_mode


def is_night_stop(night_stop: NightStopConfig, now: datetime.datetime) -> bool:
    """現在時刻が夜間停止時間帯かどうかを判定する。

    開始・終了時刻は分単位（時×60＋分）で比較する。

    - start < end の場合: start <= now < end で停止
    - start > end の場合（日またぎ、例: 21:00〜6:00）: now >= start または now < end で停止
    - start == end の場合: 一度も停止しない（常に False）
    """
    if not night_stop.enable:
        return False

    now_minutes = now.hour * 60 + now.minute
    start_minutes = night_stop.start_hour * 60 + night_stop.start_minute
    end_minutes = night_stop.end_hour * 60 + night_stop.end_minute

    if start_minutes == end_minutes:
        return False

    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes

    # 日をまたぐ場合（例: 21時〜6時）
    return now_minutes >= start_minutes or now_minutes < end_minutes


def judge_cooling_mode(config: Config, sense_data: SenseData) -> CoolingModeResult:
    logger.info("Judge cooling mode")

    night_stop = config.controller.decision.night_stop
    if is_night_stop(night_stop, my_lib.time.now()):
        logger.info("夜間停止時間帯のため、冷却モードを 0 にします")
        return CoolingModeResult(
            cooling_mode=0,
            cooler_status=StatusInfo(status=0, message="夜間停止時間帯"),
            outdoor_status=StatusInfo(status=0, message=None),
            sense_data=sense_data,
            night_stop=True,
        )

    # 閾値を config から取得
    thresholds = config.controller.decision.thresholds

    try:
        cooler_activity = unit_cooler.controller.sensor.get_cooler_activity(sense_data, thresholds)
    except RuntimeError as e:
        unit_cooler.util.notify_error(config, e.args[0])
        cooler_activity = StatusInfo(status=0, message=None)

    if cooler_activity.status == 0:
        outdoor_status = StatusInfo(status=0, message=None)
        cooling_mode = 0
    else:
        outdoor_status = unit_cooler.controller.sensor.get_outdoor_status(sense_data, thresholds)
        cooling_mode = max(cooler_activity.status + outdoor_status.status, 0)

    if cooler_activity.message is not None:
        logger.info(cooler_activity.message)
    if outdoor_status.message is not None:
        logger.info(outdoor_status.message)

    logger.info(
        "cooling_mode: %d (cooler_status: %s, outdoor_status: %s)",
        cooling_mode,
        cooler_activity.status,
        outdoor_status.status,
    )

    return CoolingModeResult(
        cooling_mode=cooling_mode,
        cooler_status=cooler_activity,
        outdoor_status=outdoor_status,
        sense_data=sense_data,
    )


def gen_control_msg(config: Config, dummy_mode: bool = False, speedup: int = 1) -> ControlMessage:
    if dummy_mode:
        mode_result = CoolingModeResult(
            cooling_mode=dummy_cooling_mode(),
            cooler_status=StatusInfo(status=0, message=None),
            outdoor_status=StatusInfo(status=0, message=None),
            sense_data=None,
        )
    else:
        # NOTE: 夜間停止時間帯はどうせモード 0 になるので、
        # センサーデータ欠損による Slack 通知を抑制する（logger.warning のみ）
        night_stop_active = is_night_stop(config.controller.decision.night_stop, my_lib.time.now())
        sense_data = unit_cooler.controller.sensor.get_sense_data(
            config, notify_failure=not night_stop_active
        )
        mode_result = judge_cooling_mode(config, sense_data)

    mode_index = min(mode_result.cooling_mode, len(unit_cooler.controller.message.CONTROL_MESSAGE_LIST) - 1)

    # 既存のメッセージリストから基本設定を取得
    template = unit_cooler.controller.message.CONTROL_MESSAGE_LIST[mode_index]

    # DutyConfig を構築（speedup 対応）
    if dummy_mode:
        duty = DutyConfig(
            enable=template.duty.enable,
            on_sec=int(max(template.duty.on_sec / speedup, ON_SEC_MIN)),
            off_sec=int(max(template.duty.off_sec / speedup, OFF_SEC_MIN)),
        )
    else:
        duty = DutyConfig(
            enable=template.duty.enable,
            on_sec=template.duty.on_sec,
            off_sec=template.duty.off_sec,
        )

    # ControlMessage を構築
    control_msg = ControlMessage(
        state=template.state,
        duty=duty,
        mode_index=mode_index,
        sense_data=mode_result.sense_data,
        cooler_status=mode_result.cooler_status,
        outdoor_status=mode_result.outdoor_status,
        night_stop=mode_result.night_stop,
    )

    logger.info(control_msg.to_dict())

    return control_msg


if __name__ == "__main__":
    # TEST Code
    import my_lib.pretty

    import unit_cooler.cli

    assert __doc__ is not None  # noqa: S101
    args, config = unit_cooler.cli.init(__doc__, name="test")

    logger.info(my_lib.pretty.format(gen_control_msg(config)))
