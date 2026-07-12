"""
省エネ効果の定量化ロジック

エアコン消費電力（InfluxDB）と散水状況（SQLite の minute_metrics）を突き合わせ、
外気温ビンごとに「散水あり」「散水なし」の平均消費電力を比較して、
散水による削減電力量・削減電気代・水道代・純益を推定します。

推定方法:
- 過去 ANALYSIS_DAYS 日間の全エアコン合算消費電力と外気温を 10 分粒度で取得
- 同じ 10 分バケットの平均 Duty 比（> 0 なら散水あり）で各バケットを分類
  （夜間停止・雨天停止の期間が自然な対照群になる）
- 外気温 1℃ 刻みのビン（TEMP_BIN_LOW 未満は除外）ごとに散水あり/なしの
  平均消費電力を比較し、差分 × 散水あり時間で削減電力量〔kWh〕を推定
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import my_lib.sensor_data
import my_lib.time

if TYPE_CHECKING:
    import unit_cooler.config
    import unit_cooler.metrics.collector

logger = logging.getLogger(__name__)

# 電気料金の目安単価〔円/kWh〕
# 出典: 公益社団法人 全国家庭電気製品公正取引協議会「電力料金目安単価」（2022年7月改定、31円/kWh）
ELECTRICITY_UNIT_PRICE = 31.0

# 分析対象期間〔日〕
ANALYSIS_DAYS = 60

# 集計バケットの幅〔分〕
BUCKET_MINUTES = 10

# 外気温ビンの範囲〔℃〕。TEMP_BIN_LOW 未満は分析対象外、TEMP_BIN_HIGH 以上は最後のビンにまとめる
TEMP_BIN_LOW = 26
TEMP_BIN_HIGH = 38

# ビンごとの比較に必要な最小サンプル数（散水あり・なしそれぞれ）
MIN_SAMPLES_PER_BIN = 3


@dataclass(frozen=True)
class EnergySample:
    """1 バケット（10 分）分の外気温・消費電力・散水有無のサンプル"""

    temperature: float  # 外気温〔℃〕
    power: float  # 全エアコン合算の平均消費電力〔W〕
    watering: bool  # 散水していたか


@dataclass(frozen=True)
class TempBinStats:
    """外気温ビンごとの散水あり/なし比較"""

    label: str
    power_on_avg: float | None  # 散水あり平均消費電力〔W〕
    power_off_avg: float | None  # 散水なし平均消費電力〔W〕
    on_count: int
    off_count: int

    @property
    def comparable(self) -> bool:
        """散水あり/なしの比較に十分なサンプルがあるか"""
        return self.on_count >= MIN_SAMPLES_PER_BIN and self.off_count >= MIN_SAMPLES_PER_BIN


@dataclass(frozen=True)
class EnergyAnalysis:
    """省エネ効果の推定結果"""

    valid: bool
    message: str
    analysis_days: int = ANALYSIS_DAYS
    bins: list[TempBinStats] = field(default_factory=list)
    watering_hours: float = 0.0  # 比較対象ビンでの散水あり時間〔h〕
    saved_energy_kwh: float = 0.0  # 推定削減電力量〔kWh〕
    saved_cost: float = 0.0  # 推定削減電気代〔円〕
    water_amount: float = 0.0  # 散水量〔L〕
    water_cost: float = 0.0  # 水道代〔円〕
    net_benefit: float = 0.0  # 純益（削減電気代 − 水道代）〔円〕

    def to_chart_dict(self) -> dict[str, Any]:
        """チャート描画用のシリアライズ（JSON 境界）"""
        return {
            "valid": self.valid,
            "labels": [b.label for b in self.bins],
            "power_on": [b.power_on_avg for b in self.bins],
            "power_off": [b.power_off_avg for b in self.bins],
            "on_counts": [b.on_count for b in self.bins],
            "off_counts": [b.off_count for b in self.bins],
        }


def insufficient_analysis(message: str) -> EnergyAnalysis:
    """データ不足時の分析結果を生成する"""
    return EnergyAnalysis(valid=False, message=message)


def bucket_key(timestamp: datetime.datetime) -> str:
    """10 分バケットのキーを生成する

    ISO 8601 文字列の先頭 15 文字（"YYYY-MM-DDTHH:M"）は分の 10 の位までを
    含むため、10 分単位のバケットキーになる。
    MetricsCollector.get_duty_by_bucket のキーと同じ形式。
    """
    return timestamp.isoformat()[:15]


def _bin_index(temperature: float) -> int | None:
    """外気温からビンのインデックスを求める（TEMP_BIN_LOW 未満は None = 対象外）"""
    if temperature < TEMP_BIN_LOW:
        return None
    return min(int(temperature) - TEMP_BIN_LOW, TEMP_BIN_HIGH - TEMP_BIN_LOW)


def _bin_label(index: int) -> str:
    """ビンのインデックスから表示ラベルを生成する"""
    low = TEMP_BIN_LOW + index
    if low >= TEMP_BIN_HIGH:
        return f"{TEMP_BIN_HIGH}℃〜"
    return f"{low}〜{low + 1}℃"


def analyze_energy_savings(
    samples: list[EnergySample],
    water_amount: float,
    water_cost: float,
    slot_hours: float = BUCKET_MINUTES / 60,
    electricity_unit_price: float = ELECTRICITY_UNIT_PRICE,
    analysis_days: int = ANALYSIS_DAYS,
) -> EnergyAnalysis:
    """サンプル列から省エネ効果を推定する（純粋関数）

    外気温ビンごとに散水あり/なしの平均消費電力を比較し、
    「(散水なし平均 − 散水あり平均) × 散水あり時間」を削減電力量として合算する。
    比較可能な（両群に MIN_SAMPLES_PER_BIN 以上のサンプルがある）ビンのみ合算対象。
    """
    bin_count = TEMP_BIN_HIGH - TEMP_BIN_LOW + 1
    on_values: list[list[float]] = [[] for _ in range(bin_count)]
    off_values: list[list[float]] = [[] for _ in range(bin_count)]

    for sample in samples:
        index = _bin_index(sample.temperature)
        if index is None:
            continue
        (on_values if sample.watering else off_values)[index].append(sample.power)

    bins: list[TempBinStats] = []
    saved_energy_kwh = 0.0
    watering_hours = 0.0
    has_comparable_bin = False

    for index in range(bin_count):
        on = on_values[index]
        off = off_values[index]
        on_avg = sum(on) / len(on) if on else None
        off_avg = sum(off) / len(off) if off else None
        stats = TempBinStats(
            label=_bin_label(index),
            power_on_avg=on_avg,
            power_off_avg=off_avg,
            on_count=len(on),
            off_count=len(off),
        )
        bins.append(stats)

        # NOTE: comparable が真なら両群にサンプルがあるため avg は非 None（型の絞り込みを兼ねる）
        if stats.comparable and on_avg is not None and off_avg is not None:
            has_comparable_bin = True
            saved_energy_kwh += (off_avg - on_avg) * stats.on_count * slot_hours / 1000.0
            watering_hours += stats.on_count * slot_hours

    if not has_comparable_bin:
        return EnergyAnalysis(
            valid=False,
            message="散水あり・なしを比較できる外気温帯のデータが不足しています",
            analysis_days=analysis_days,
            bins=bins,
            water_amount=water_amount,
            water_cost=water_cost,
        )

    saved_cost = saved_energy_kwh * electricity_unit_price
    return EnergyAnalysis(
        valid=True,
        message=(
            f"外気温 {TEMP_BIN_LOW}℃ 以上の 1℃ 刻みビンごとに、散水あり/なしの平均消費電力を比較した推定値"
        ),
        analysis_days=analysis_days,
        bins=bins,
        watering_hours=watering_hours,
        saved_energy_kwh=saved_energy_kwh,
        saved_cost=saved_cost,
        water_amount=water_amount,
        water_cost=water_cost,
        net_benefit=saved_cost - water_cost,
    )


def _result_to_bucket_map(result: my_lib.sensor_data.SensorDataResult | BaseException) -> dict[str, float]:
    """センサーデータ取得結果を 10 分バケットのマップに変換する"""
    if isinstance(result, BaseException):
        logger.warning("Sensor data fetch failed: %s", result)
        return {}
    if not result.valid:
        return {}
    return {bucket_key(timestamp): value for timestamp, value in zip(result.time, result.value, strict=True)}


def collect_energy_analysis(
    config: unit_cooler.config.Config,
    collector: unit_cooler.metrics.collector.MetricsCollector,
) -> EnergyAnalysis:
    """InfluxDB と SQLite からデータを取得して省エネ効果を推定する"""
    power_sensors = list(config.controller.sensor.power)
    temp_sensors = list(config.controller.sensor.temp)
    if not power_sensors or not temp_sensors:
        return insufficient_analysis("電力・外気温センサーが設定されていません")

    start = f"-{ANALYSIS_DAYS * 24}h"
    temp_sensor = temp_sensors[0]
    requests = [
        my_lib.sensor_data.DataRequest(
            measure=temp_sensor.measure,
            hostname=temp_sensor.hostname,
            field="temp",
            start=start,
            every_min=BUCKET_MINUTES,
            window_min=BUCKET_MINUTES,
        )
    ]
    requests.extend(
        my_lib.sensor_data.DataRequest(
            measure=sensor.measure,
            hostname=sensor.hostname,
            field="power",
            start=start,
            every_min=BUCKET_MINUTES,
            window_min=BUCKET_MINUTES,
        )
        for sensor in power_sensors
    )

    results = asyncio.run(my_lib.sensor_data.fetch_data_parallel(config.controller.influxdb, requests))

    temp_by_bucket = _result_to_bucket_map(results[0])
    if not temp_by_bucket:
        return insufficient_analysis("外気温データを取得できませんでした")

    # 全エアコンの合算消費電力（欠測で合算が過小になるのを避けるため、
    # 有効な全系列のデータが揃ったバケットのみ採用する）
    power_sums: dict[str, float] = {}
    power_counts: dict[str, int] = {}
    valid_series = 0
    for result in results[1:]:
        series = _result_to_bucket_map(result)
        if not series:
            continue
        valid_series += 1
        for key, value in series.items():
            power_sums[key] = power_sums.get(key, 0.0) + value
            power_counts[key] = power_counts.get(key, 0) + 1

    if valid_series == 0:
        return insufficient_analysis("エアコン消費電力データを取得できませんでした")

    duty_by_bucket = collector.get_duty_by_bucket(my_lib.time.now() - datetime.timedelta(days=ANALYSIS_DAYS))
    if not duty_by_bucket:
        return insufficient_analysis("散水メトリクス（Duty 比）がありません")

    samples: list[EnergySample] = []
    for key, power_sum in power_sums.items():
        if power_counts[key] != valid_series:
            continue
        temperature = temp_by_bucket.get(key)
        duty = duty_by_bucket.get(key)
        if temperature is None or duty is None:
            continue
        samples.append(EnergySample(temperature=temperature, power=power_sum, watering=duty > 0))

    watering_config = config.controller.watering
    water_amount = my_lib.sensor_data.get_day_sum(
        config.controller.influxdb,
        watering_config.measure,
        watering_config.hostname,
        "flow",
        ANALYSIS_DAYS,
    )
    water_cost = water_amount * watering_config.unit_price / 1000.0

    return analyze_energy_savings(samples, water_amount=water_amount, water_cost=water_cost)
