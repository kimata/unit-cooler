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
from typing import Any

import my_lib.sensor_data
import my_lib.time
from my_lib.sensor_data import DataRequest

import unit_cooler.const
import unit_cooler.util
from unit_cooler.config import Config, DecisionThresholdsConfig, SensorItemConfig

# デフォルト閾値（config.yaml で指定がない場合に使用）
_DEFAULT_THRESHOLDS: dict[str, Any] = dataclasses.asdict(DecisionThresholdsConfig.default())

COOLER_ACTIVITY_LIST = [
    {
        "judge": lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.FULL] >= 2,
        "message": "2 台以上のエアコンがフル稼働しています。(cooler_status: 6)",
        "status": 6,
    },
    {
        "judge": lambda mode_map: (mode_map[unit_cooler.const.AIRCON_MODE.FULL] >= 1)
        and (mode_map[unit_cooler.const.AIRCON_MODE.NORMAL] >= 1),
        "message": "複数台ののエアコンがフル稼働もしくは平常運転しています。(cooler_status: 5)",
        "status": 5,
    },
    {
        "judge": lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.FULL] >= 1,
        "message": "1 台以上のエアコンがフル稼働しています。(cooler_status: 4)",
        "status": 4,
    },
    {
        "judge": lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.NORMAL] >= 2,
        "message": "2 台以上のエアコンが平常運転しています。(cooler_status: 4)",
        "status": 4,
    },
    {
        "judge": lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.NORMAL] >= 1,
        "message": "1 台以上のエアコンが平常運転しています。(cooler_status: 3)",
        "status": 3,
    },
    {
        "judge": lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.IDLE] >= 2,
        "message": "2 台以上のエアコンがアイドル運転しています。(cooler_status: 2)",
        "status": 2,
    },
    {
        "judge": lambda mode_map: mode_map[unit_cooler.const.AIRCON_MODE.IDLE] >= 1,
        "message": "1 台以上のエアコンがアイドル運転しています。(cooler_status: 1)",
        "status": 1,
    },
    {
        "judge": lambda mode_map: True,
        "message": "エアコンは稼働していません。(cooler_status: 0)",
        "status": 0,
    },
]


OUTDOOR_CONDITION_LIST = [
    {
        "judge": lambda sense_data: sense_data["rain"][0]["value"] > _DEFAULT_THRESHOLDS["rain_max"],
        "message": lambda sense_data: (
            "雨が降っているので ({rain:.1f} mm/h) 冷却を停止します。(outdoor_status: -4)"
        ).format(rain=sense_data["rain"][0]["value"]),
        "status": -4,
    },
    {
        "judge": lambda sense_data: sense_data["humi"][0]["value"] > _DEFAULT_THRESHOLDS["humi_max"],
        "message": lambda sense_data: (
            "湿度 ({humi:.1f} %) が {threshold:.1f} % より高いので冷却を停止します。(outdoor_status: -4)"
        ).format(humi=sense_data["humi"][0]["value"], threshold=_DEFAULT_THRESHOLDS["humi_max"]),
        "status": -4,
    },
    {
        "judge": lambda sense_data: (sense_data["temp"][0]["value"] > _DEFAULT_THRESHOLDS["temp_high_h"])
        and (sense_data["solar_rad"][0]["value"] > _DEFAULT_THRESHOLDS["solar_rad_daytime"]),
        "message": lambda sense_data: (
            "日射量 ({solar_rad:,.0f} W/m^2) が "
            "{solar_rad_threshold:,.0f} W/m^2 より大きく、"
            "外気温 ({temp:.1f} ℃) が "
            "{threshold:.1f} ℃ より高いので冷却を大きく強化します。(outdoor_status: 3)"
        ).format(
            solar_rad=sense_data["solar_rad"][0]["value"],
            solar_rad_threshold=_DEFAULT_THRESHOLDS["solar_rad_daytime"],
            temp=sense_data["temp"][0]["value"],
            threshold=_DEFAULT_THRESHOLDS["temp_high_h"],
        ),
        "status": 3,
    },
    {
        "judge": lambda sense_data: (sense_data["temp"][0]["value"] > _DEFAULT_THRESHOLDS["temp_high_l"])
        and (sense_data["solar_rad"][0]["value"] > _DEFAULT_THRESHOLDS["solar_rad_daytime"]),
        "message": lambda sense_data: (
            "日射量 ({solar_rad:,.0f} W/m^2) が "
            "{solar_rad_threshold:,.0f} W/m^2 より大きく、"
            "外気温 ({temp:.1f} ℃) が "
            "{threshold:.1f} ℃ より高いので冷却を強化します。(outdoor_status: 2)"
        ).format(
            solar_rad=sense_data["solar_rad"][0]["value"],
            solar_rad_threshold=_DEFAULT_THRESHOLDS["solar_rad_daytime"],
            temp=sense_data["temp"][0]["value"],
            threshold=_DEFAULT_THRESHOLDS["temp_high_l"],
        ),
        "status": 2,
    },
    {
        "judge": lambda sense_data: (
            sense_data["solar_rad"][0]["value"] > _DEFAULT_THRESHOLDS["solar_rad_high"]
        ),
        "message": lambda sense_data: (
            "日射量 ({solar_rad:,.0f} W/m^2) が "
            "{threshold:,.0f} W/m^2 より大きいので冷却を少し強化します。(outdoor_status: 1)"
        ).format(
            solar_rad=sense_data["solar_rad"][0]["value"],
            threshold=_DEFAULT_THRESHOLDS["solar_rad_high"],
        ),
        "status": 1,
    },
    {
        "judge": lambda sense_data: (sense_data["temp"][0]["value"] > _DEFAULT_THRESHOLDS["temp_mid"])
        and (sense_data["lux"][0]["value"] < _DEFAULT_THRESHOLDS["lux"]),
        "message": lambda sense_data: (
            " 外気温 ({temp:.1f} ℃) が {temp_threshold:.1f} ℃ より高いものの、"
            "照度 ({lux:,.0f} LUX) が {lux_threshold:,.0f} LUX より小さいので、"
            "冷却を少し弱めます。(outdoor_status: -1)"
        ).format(
            temp=sense_data["temp"][0]["value"],
            temp_threshold=_DEFAULT_THRESHOLDS["temp_mid"],
            lux=sense_data["lux"][0]["value"],
            lux_threshold=_DEFAULT_THRESHOLDS["lux"],
        ),
        "status": -1,
    },
    {
        "judge": lambda sense_data: sense_data["lux"][0]["value"] < _DEFAULT_THRESHOLDS["lux"],
        "message": lambda sense_data: (
            "照度 ({lux:,.0f} LUX) が {threshold:,.0f} LUX より小さいので冷却を弱めます。(outdoor_status: -2)"
        ).format(lux=sense_data["lux"][0]["value"], threshold=_DEFAULT_THRESHOLDS["lux"]),
        "status": -2,
    },
    {
        "judge": lambda sense_data: (
            sense_data["solar_rad"][0]["value"] < _DEFAULT_THRESHOLDS["solar_rad_low"]
        ),
        "message": lambda sense_data: (
            "日射量 ({solar_rad:,.0f} W/m^2) が "
            "{threshold:,.0f} W/m^2 より小さいので冷却を少し弱めます。(outdoor_status: -1)"
        ).format(
            solar_rad=sense_data["solar_rad"][0]["value"],
            threshold=_DEFAULT_THRESHOLDS["solar_rad_low"],
        ),
        "status": -1,
    },
]


# NOTE: 外部環境の状況を評価する。
# (数字が大きいほど冷却を強める)
def get_outdoor_status(
    sense_data: dict[str, list[dict[str, Any]]],
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """外部環境の状況を評価する

    Args:
        sense_data: センサーデータ
        thresholds: 閾値（指定しない場合はデフォルト値を使用）

    Returns:
        外部環境の状況（status と message を含む dict）
    """
    # 閾値を取得（指定がない場合はデフォルト値）
    th = thresholds if thresholds else _DEFAULT_THRESHOLDS
    rain_max = th["rain_max"]
    humi_max = th["humi_max"]
    temp_high_h = th["temp_high_h"]
    temp_high_l = th["temp_high_l"]
    temp_mid = th["temp_mid"]
    solar_rad_daytime = th["solar_rad_daytime"]
    solar_rad_high = th["solar_rad_high"]
    solar_rad_low = th["solar_rad_low"]
    lux = th["lux"]

    temp_str = (
        f"{sense_data['temp'][0]['value']:.1f}" if sense_data["temp"][0]["value"] is not None else "？",
    )
    humi_str = (
        f"{sense_data['humi'][0]['value']:.1f}" if sense_data["humi"][0]["value"] is not None else "？",
    )
    solar_rad_str = (
        f"{sense_data['solar_rad'][0]['value']:,.0f}"
        if sense_data["solar_rad"][0]["value"] is not None
        else "？",
    )
    lux_str = (
        f"{sense_data['lux'][0]['value']:,.0f}" if sense_data["lux"][0]["value"] is not None else "？",
    )

    logging.info(
        "気温: %s ℃, 湿度: %s %%, 日射量: %s W/m^2, 照度: %s LUX", temp_str, humi_str, solar_rad_str, lux_str
    )

    is_senser_valid = all(
        sense_data[key][0]["value"] is not None for key in ["temp", "humi", "solar_rad", "lux"]
    )

    if not is_senser_valid:
        return {"status": -10, "message": "センサーデータが欠落していますので、冷却を停止します。"}

    # 各条件をチェック（閾値を使用）
    rain_val = sense_data["rain"][0]["value"]
    humi_val = sense_data["humi"][0]["value"]
    temp_val = sense_data["temp"][0]["value"]
    solar_rad_val = sense_data["solar_rad"][0]["value"]
    lux_val = sense_data["lux"][0]["value"]

    if rain_val > rain_max:
        return {
            "status": -4,
            "message": f"雨が降っているので ({rain_val:.1f} mm/h) 冷却を停止します。(outdoor_status: -4)",
        }

    if humi_val > humi_max:
        return {
            "status": -4,
            "message": (
                f"湿度 ({humi_val:.1f} %) が {humi_max:.1f} % より高いので"
                "冷却を停止します。(outdoor_status: -4)"
            ),
        }

    if temp_val > temp_high_h and solar_rad_val > solar_rad_daytime:
        return {
            "status": 3,
            "message": (
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_daytime:,.0f} W/m^2 より大きく、"
                f"外気温 ({temp_val:.1f} ℃) が {temp_high_h:.1f} ℃ より高いので"
                "冷却を大きく強化します。(outdoor_status: 3)"
            ),
        }

    if temp_val > temp_high_l and solar_rad_val > solar_rad_daytime:
        return {
            "status": 2,
            "message": (
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_daytime:,.0f} W/m^2 より大きく、"
                f"外気温 ({temp_val:.1f} ℃) が {temp_high_l:.1f} ℃ より高いので"
                "冷却を強化します。(outdoor_status: 2)"
            ),
        }

    if solar_rad_val > solar_rad_high:
        return {
            "status": 1,
            "message": (
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_high:,.0f} W/m^2 より大きいので"
                "冷却を少し強化します。(outdoor_status: 1)"
            ),
        }

    if temp_val > temp_mid and lux_val < lux:
        return {
            "status": -1,
            "message": (
                f"外気温 ({temp_val:.1f} ℃) が {temp_mid:.1f} ℃ より高いものの、"
                f"照度 ({lux_val:,.0f} LUX) が {lux:,.0f} LUX より小さいので、"
                "冷却を少し弱めます。(outdoor_status: -1)"
            ),
        }

    if lux_val < lux:
        return {
            "status": -2,
            "message": (
                f"照度 ({lux_val:,.0f} LUX) が {lux:,.0f} LUX より小さいので"
                "冷却を弱めます。(outdoor_status: -2)"
            ),
        }

    if solar_rad_val < solar_rad_low:
        return {
            "status": -1,
            "message": (
                f"日射量 ({solar_rad_val:,.0f} W/m^2) が {solar_rad_low:,.0f} W/m^2 より小さいので"
                "冷却を少し弱めます。(outdoor_status: -1)"
            ),
        }

    return {"status": 0, "message": None}


# NOTE: クーラーの稼働状況を評価する。
# (数字が大きいほど稼働状況が活発)
def get_cooler_activity(
    sense_data: dict[str, list[dict[str, Any]]],
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """クーラーの稼働状況を評価する

    Args:
        sense_data: センサーデータ
        thresholds: 閾値（指定しない場合はデフォルト値を使用）

    Returns:
        稼働状況（status と message を含む dict）
    """
    mode_map: dict[unit_cooler.const.AIRCON_MODE, int] = {}

    for mode in unit_cooler.const.AIRCON_MODE:
        mode_map[mode] = 0

    temp = sense_data["temp"][0]["value"]
    for aircon_power in sense_data["power"]:
        mode = get_cooler_state(aircon_power, temp, thresholds)
        mode_map[mode] += 1

    logging.info(mode_map)

    for condition in COOLER_ACTIVITY_LIST:
        if condition["judge"](mode_map):  # type: ignore[operator]
            return {
                "status": condition["status"],
                "message": condition["message"],
            }
    raise AssertionError("This should never be reached.")  # pragma: no cover


def get_cooler_state(
    aircon_power: dict[str, Any],
    temp: float | None,
    thresholds: dict[str, Any] | None = None,
) -> unit_cooler.const.AIRCON_MODE:
    """エアコンの動作モードを判定する

    Args:
        aircon_power: エアコンの消費電力データ
        temp: 外気温
        thresholds: 閾値（指定しない場合はデフォルト値を使用）

    Returns:
        エアコンの動作モード
    """
    # 閾値を取得（指定がない場合はデフォルト値）
    th = thresholds if thresholds else _DEFAULT_THRESHOLDS
    temp_cooling = th["temp_cooling"]
    power_full = th["power_full"]
    power_normal = th["power_normal"]
    power_work = th["power_work"]

    mode = unit_cooler.const.AIRCON_MODE.OFF
    if temp is None:
        # NOTE: 外気温がわからないと暖房と冷房の区別がつかないので、致命的エラー扱いにする
        raise RuntimeError("外気温が不明のため、エアコン動作モードを判断できません。")

    if aircon_power["value"] is None:
        logging.warning(
            "%s の消費電力が不明のため、動作モードを判断できません。OFFとみなします。", aircon_power["name"]
        )
        return unit_cooler.const.AIRCON_MODE.OFF

    if temp >= temp_cooling:
        if aircon_power["value"] > power_full:
            mode = unit_cooler.const.AIRCON_MODE.FULL
        elif aircon_power["value"] > power_normal:
            mode = unit_cooler.const.AIRCON_MODE.NORMAL
        elif aircon_power["value"] > power_work:
            mode = unit_cooler.const.AIRCON_MODE.IDLE

    logging.info(
        "%s: %s W, 外気温: %.1f ℃  (mode: %s)",
        aircon_power["name"],
        f"{aircon_power['value']:,.0f}",
        temp,
        mode,
    )

    return mode


def get_sense_data(config: Config) -> dict[str, list[dict[str, Any]]]:
    if os.environ.get("DUMMY_MODE", "false") == "true":
        start = "-169h"
        stop = "-168h"
    else:
        start = "-1h"
        stop = "now()"

    zoneinfo = my_lib.time.get_zoneinfo()
    influxdb_config = {
        "url": config.controller.influxdb.url,
        "token": config.controller.influxdb.token,
        "org": config.controller.influxdb.org,
        "bucket": config.controller.influxdb.bucket,
    }

    # センサー種別とセンサーリストのマッピング
    sensor_kinds = {
        "temp": config.controller.sensor.temp,
        "humi": config.controller.sensor.humi,
        "lux": config.controller.sensor.lux,
        "solar_rad": config.controller.sensor.solar_rad,
        "rain": config.controller.sensor.rain,
        "power": config.controller.sensor.power,
    }

    # 全センサーの DataRequest を作成
    requests: list[DataRequest] = []
    request_info: list[tuple[str, SensorItemConfig]] = []  # (kind, sensor) のペア

    for kind, sensors in sensor_kinds.items():
        for sensor in sensors:
            requests.append(
                DataRequest(
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
    results = asyncio.run(
        my_lib.sensor_data.fetch_data_parallel(influxdb_config, requests)  # type: ignore[arg-type]
    )

    # 結果を元の構造に再構築
    sense_data: dict[str, list[dict[str, Any]]] = {kind: [] for kind in sensor_kinds}
    failed_sensors: list[str] = []

    for (kind, sensor), result in zip(request_info, results, strict=True):
        if isinstance(result, BaseException):
            logging.warning("Failed to fetch %s data for %s: %s", kind, sensor.name, result)
            sense_data[kind].append({"name": sensor.name, "value": None})
            failed_sensors.append(sensor.name)
        elif result.valid:
            value = result.value[0]
            if kind == "rain":
                # NOTE: 観測している雨量は1分間の降水量なので、1時間雨量に換算
                value *= 60
            sense_data[kind].append(
                {
                    "name": sensor.name,
                    "time": result.time[0].replace(tzinfo=zoneinfo),
                    "value": value,
                }
            )
        else:
            sense_data[kind].append({"name": sensor.name, "value": None})
            failed_sensors.append(sensor.name)

    # まとめてエラー通知
    if failed_sensors:
        sensor_names = "、".join(failed_sensors)
        unit_cooler.util.notify_error(
            config,
            f"次のセンサーのデータを取得できませんでした: {sensor_names}",
        )

    return sense_data


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.logger
    import my_lib.pretty

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = Config.load(config_file)

    sense_data = get_sense_data(config)

    logging.info(my_lib.pretty.format(sense_data))
    logging.info(my_lib.pretty.format(get_outdoor_status(sense_data)))
    logging.info(my_lib.pretty.format(get_cooler_activity(sense_data)))
