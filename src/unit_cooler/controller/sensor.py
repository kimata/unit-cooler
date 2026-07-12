#!/usr/bin/env python3
"""
InfluxDB から制御用のセンシングデータを取得します。

Usage:
  sensor.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import asyncio
import dataclasses
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

import my_lib.sensor_data
import my_lib.time

import unit_cooler.const
import unit_cooler.util
from unit_cooler.config import Config, DecisionThresholdsConfig, SensorConfig, SensorItemConfig
from unit_cooler.messages import SenseData, SensorReading, StatusInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoolerActivityCondition:
    """エアコン稼働状況の判定条件"""

    judge: Callable[[dict[unit_cooler.const.AIRCON_MODE, int]], bool]
    message: str
    status: int


COOLER_ACTIVITY_LIST: list[CoolerActivityCondition] = [
    CoolerActivityCondition(
        judge=lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.FULL] >= 2,
        message="2 台以上のエアコンがフル稼働しています。(cooler_status: 6)",
        status=6,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: (mode_map[unit_cooler.const.AIRCON_MODE.FULL] >= 1)
        and (mode_map[unit_cooler.const.AIRCON_MODE.NORMAL] >= 1),
        message="複数台ののエアコンがフル稼働もしくは平常運転しています。(cooler_status: 5)",
        status=5,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.FULL] >= 1,
        message="1 台以上のエアコンがフル稼働しています。(cooler_status: 4)",
        status=4,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.NORMAL] >= 2,
        message="2 台以上のエアコンが平常運転しています。(cooler_status: 4)",
        status=4,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.NORMAL] >= 1,
        message="1 台以上のエアコンが平常運転しています。(cooler_status: 3)",
        status=3,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.IDLE] >= 2,
        message="2 台以上のエアコンがアイドル運転しています。(cooler_status: 2)",
        status=2,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.IDLE] >= 1,
        message="1 台以上のエアコンがアイドル運転しています。(cooler_status: 1)",
        status=1,
    ),
    CoolerActivityCondition(
        judge=lambda mode_map: True,
        message="エアコンは稼働していません。(cooler_status: 0)",
        status=0,
    ),
]


# NOTE: 外部環境の状況を評価する。
# (数字が大きいほど冷却を強める)
def get_outdoor_status(
    sense_data: SenseData,
    thresholds: DecisionThresholdsConfig,
) -> StatusInfo:
    """外部環境の状況を評価する

    Args:
        sense_data: センサーデータ
        thresholds: 判定閾値

    Returns:
        外部環境の状況（StatusInfo dataclass）
    """
    temp_val = sense_data.first_value("temp")
    humi_val = sense_data.first_value("humi")
    solar_rad_val = sense_data.first_value("solar_rad")
    lux_val = sense_data.first_value("lux")
    rain_val = sense_data.first_value("rain")

    logger.info(
        "気温: %s ℃, 湿度: %s %%, 日射量: %s W/m^2, 照度: %s LUX",
        f"{temp_val:.1f}" if temp_val is not None else "？",
        f"{humi_val:.1f}" if humi_val is not None else "？",
        f"{solar_rad_val:,.0f}" if solar_rad_val is not None else "？",
        f"{lux_val:,.0f}" if lux_val is not None else "？",
    )

    # NOTE: チェック対象を SenseData のフィールド定義から導出することで、
    # センサー追加時のチェック漏れを防ぐ
    is_sensor_valid = all(
        sense_data.first_value(key) is not None for key in SenseData.environment_field_names()
    )

    if not is_sensor_valid:
        return StatusInfo(status=-10, message="センサーデータが欠落していますので、冷却を停止します。")

    # 型の絞り込み（is_sensor_valid チェック済みのため None ではない）
    assert temp_val is not None  # noqa: S101
    assert humi_val is not None  # noqa: S101
    assert solar_rad_val is not None  # noqa: S101
    assert lux_val is not None  # noqa: S101
    assert rain_val is not None  # noqa: S101

    rain_max = thresholds.rain_max
    humi_max = thresholds.humi_max
    temp_high_h = thresholds.temp_high_h
    temp_high_l = thresholds.temp_high_l
    temp_mid = thresholds.temp_mid
    solar_rad_daytime = thresholds.solar_rad_daytime
    solar_rad_high = thresholds.solar_rad_high
    solar_rad_low = thresholds.solar_rad_low
    lux = thresholds.lux

    if rain_val > rain_max:
        return StatusInfo(
            status=-4,
            message=f"雨が降っているので ({rain_val:.1f} mm/h) 冷却を停止します。(outdoor_status: -4)",
        )

    if humi_val > humi_max:
        return StatusInfo(
            status=-4,
            message=(
                f"湿度 ({humi_val:.1f} %) が {humi_max:.1f} % より高いので"
                "冷却を停止します。(outdoor_status: -4)"
            ),
        )

    if temp_val > temp_high_h and solar_rad_val > solar_rad_daytime:
        return StatusInfo(
            status=3,
            message=(
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_daytime:,.0f} W/m^2 より大きく、"
                f"外気温 ({temp_val:.1f} ℃) が {temp_high_h:.1f} ℃ より高いので"
                "冷却を大きく強化します。(outdoor_status: 3)"
            ),
        )

    if temp_val > temp_high_l and solar_rad_val > solar_rad_daytime:
        return StatusInfo(
            status=2,
            message=(
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_daytime:,.0f} W/m^2 より大きく、"
                f"外気温 ({temp_val:.1f} ℃) が {temp_high_l:.1f} ℃ より高いので"
                "冷却を強化します。(outdoor_status: 2)"
            ),
        )

    if solar_rad_val > solar_rad_high:
        return StatusInfo(
            status=1,
            message=(
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_high:,.0f} W/m^2 より大きいので"
                "冷却を少し強化します。(outdoor_status: 1)"
            ),
        )

    if temp_val > temp_mid and lux_val < lux:
        return StatusInfo(
            status=-1,
            message=(
                f"外気温 ({temp_val:.1f} ℃) が {temp_mid:.1f} ℃ より高いものの、"
                f"照度 ({lux_val:,.0f} LUX) が {lux:,.0f} LUX より小さいので、"
                "冷却を少し弱めます。(outdoor_status: -1)"
            ),
        )

    if lux_val < lux:
        return StatusInfo(
            status=-2,
            message=(
                f"照度 ({lux_val:,.0f} LUX) が {lux:,.0f} LUX より小さいので"
                "冷却を弱めます。(outdoor_status: -2)"
            ),
        )

    if solar_rad_val < solar_rad_low:
        return StatusInfo(
            status=-1,
            message=(
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_low:,.0f} W/m^2 より小さいので"
                "冷却を少し弱めます。(outdoor_status: -1)"
            ),
        )

    return StatusInfo(status=0, message=None)


# NOTE: クーラーの稼働状況を評価する。
# (数字が大きいほど稼働状況が活発)
def get_cooler_activity(
    sense_data: SenseData,
    thresholds: DecisionThresholdsConfig,
) -> StatusInfo:
    """クーラーの稼働状況を評価する

    Args:
        sense_data: センサーデータ
        thresholds: 判定閾値

    Returns:
        稼働状況（StatusInfo dataclass）
    """
    mode_map: dict[unit_cooler.const.AIRCON_MODE, int] = {}

    for mode in unit_cooler.const.AIRCON_MODE:
        mode_map[mode] = 0

    temp = sense_data.first_value("temp")
    for aircon_power in sense_data.power:
        mode = get_cooler_state(aircon_power, temp, thresholds)
        mode_map[mode] += 1

    logger.info(mode_map)

    for condition in COOLER_ACTIVITY_LIST:
        if condition.judge(mode_map):
            return StatusInfo(
                status=condition.status,
                message=condition.message,
            )
    raise AssertionError("This should never be reached.")  # pragma: no cover


def get_cooler_state(
    aircon_power: SensorReading,
    temp: float | None,
    thresholds: DecisionThresholdsConfig,
) -> unit_cooler.const.AIRCON_MODE:
    """エアコンの動作モードを判定する

    Args:
        aircon_power: エアコンの消費電力データ
        temp: 外気温
        thresholds: 判定閾値

    Returns:
        エアコンの動作モード
    """
    mode = unit_cooler.const.AIRCON_MODE.OFF
    if temp is None:
        # NOTE: 外気温がわからないと暖房と冷房の区別がつかないので、致命的エラー扱いにする
        raise RuntimeError("外気温が不明のため、エアコン動作モードを判断できません。")

    if aircon_power.value is None:
        logger.warning(
            "%s の消費電力が不明のため、動作モードを判断できません。OFFとみなします。", aircon_power.name
        )
        return unit_cooler.const.AIRCON_MODE.OFF

    if temp >= thresholds.temp_cooling:
        if aircon_power.value > thresholds.power_full:
            mode = unit_cooler.const.AIRCON_MODE.FULL
        elif aircon_power.value > thresholds.power_normal:
            mode = unit_cooler.const.AIRCON_MODE.NORMAL
        elif aircon_power.value > thresholds.power_work:
            mode = unit_cooler.const.AIRCON_MODE.IDLE

    logger.info(
        "%s: %s W, 外気温: %.1f ℃  (mode: %s)",
        aircon_power.name,
        f"{aircon_power.value:,.0f}",
        temp,
        mode,
    )

    return mode


def get_sense_data(config: Config, notify_failure: bool = True) -> SenseData:
    """InfluxDB からセンサーデータを取得する

    Args:
        config: 設定
        notify_failure: 取得失敗時に Slack 通知するか。
            False の場合は logger.warning のみ（夜間停止時間帯の通知抑制用）。

    Returns:
        センサーデータ
    """
    if os.environ.get("DUMMY_MODE", "false") == "true":
        start = "-169h"
        stop = "-168h"
    else:
        start = "-1h"
        stop = "now()"

    zoneinfo = my_lib.time.get_zoneinfo()
    influxdb_config = config.controller.influxdb

    # センサー種別とセンサーリストのマッピング
    # NOTE: SensorConfig のフィールド定義から導出することで、センサー追加時の漏れを防ぐ
    sensor_kinds: dict[str, list[SensorItemConfig]] = {
        field.name: getattr(config.controller.sensor, field.name)
        for field in dataclasses.fields(SensorConfig)
    }

    # 全センサーの DataRequest を作成
    requests: list[my_lib.sensor_data.DataRequest] = []
    request_info: list[tuple[str, SensorItemConfig]] = []  # (kind, sensor) のペア

    for kind, sensors in sensor_kinds.items():
        for sensor in sensors:
            requests.append(
                my_lib.sensor_data.DataRequest(
                    measure=sensor.measure,
                    hostname=sensor.hostname,
                    field=kind,
                    start=start,
                    stop=stop,
                    last=True,
                )
            )
            request_info.append((kind, sensor))

    # 並列でデータ取得
    results = asyncio.run(my_lib.sensor_data.fetch_data_parallel(influxdb_config, requests))

    # 結果を元の構造に再構築
    readings: dict[str, list[SensorReading]] = {kind: [] for kind in sensor_kinds}
    failed_sensors: list[str] = []

    for (kind, sensor), result in zip(request_info, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("Failed to fetch %s data for %s: %s", kind, sensor.name, result)
            readings[kind].append(SensorReading(name=sensor.name, value=None))
            failed_sensors.append(sensor.name)
        elif result.valid:
            value = result.value[0]
            if kind == "rain":
                # NOTE: 観測している雨量は1分間の降水量なので、1時間雨量に換算
                value *= 60
            readings[kind].append(
                SensorReading(
                    name=sensor.name,
                    value=value,
                    time=result.time[0].replace(tzinfo=zoneinfo),
                )
            )
        else:
            readings[kind].append(SensorReading(name=sensor.name, value=None))
            failed_sensors.append(sensor.name)

    # まとめてエラー通知
    if failed_sensors:
        sensor_names = "、".join(failed_sensors)
        message = f"次のセンサーのデータを取得できませんでした: {sensor_names}"
        if notify_failure:
            unit_cooler.util.notify_error(config, message)
        else:
            logger.warning(message)

    return SenseData(**readings)
