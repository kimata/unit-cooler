#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.metrics.energy のテスト（合成データによる純粋関数のテスト）"""

from __future__ import annotations

import datetime
import zoneinfo

import pytest

import unit_cooler.metrics.energy as energy

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")


def make_samples(
    temperature: float, power_on: float, power_off: float, count: int = 5
) -> list[energy.EnergySample]:
    """指定した外気温で散水あり/なしのサンプルを count 個ずつ生成する"""
    samples = []
    for _ in range(count):
        samples.append(energy.EnergySample(temperature=temperature, power=power_on, watering=True))
        samples.append(energy.EnergySample(temperature=temperature, power=power_off, watering=False))
    return samples


class TestBucketKey:
    """bucket_key のテスト"""

    def test_floors_to_ten_minutes(self):
        """10 分単位に切り捨てられる"""
        base = datetime.datetime(2024, 7, 1, 14, 35, 42, tzinfo=TIMEZONE)
        assert energy.bucket_key(base) == "2024-07-01T14:3"
        assert energy.bucket_key(base.replace(minute=30, second=0)) == "2024-07-01T14:3"
        assert energy.bucket_key(base.replace(minute=40)) == "2024-07-01T14:4"
        assert energy.bucket_key(base.replace(minute=5)) == "2024-07-01T14:0"

    def test_matches_collector_bucket(self, tmp_path):
        """MetricsCollector.get_duty_by_bucket のキーと形式が一致する"""
        from unit_cooler.metrics.collector import MetricsCollector

        holder = {"time": datetime.datetime(2024, 7, 1, 14, 35, 0, tzinfo=TIMEZONE)}
        collector = MetricsCollector(tmp_path / "metrics.db", time_func=lambda: holder["time"])
        collector.update_duty_ratio(30.0, 60.0)
        collector.close()  # 14:35 の行として保存される

        duty = collector.get_duty_by_bucket(datetime.datetime(2024, 7, 1, 0, 0, 0, tzinfo=TIMEZONE))
        key = energy.bucket_key(datetime.datetime(2024, 7, 1, 14, 35, 0, tzinfo=TIMEZONE))
        assert key in duty
        assert duty[key] == pytest.approx(0.5, rel=0.01)


class TestBinIndex:
    """外気温ビン割り当てのテスト"""

    def test_below_low_is_excluded(self):
        """下限未満は対象外"""
        assert energy._bin_index(25.9) is None
        assert energy._bin_index(10.0) is None

    def test_one_degree_bins(self):
        """1℃ 刻みで割り当てられる"""
        assert energy._bin_index(26.0) == 0
        assert energy._bin_index(26.9) == 0
        assert energy._bin_index(27.0) == 1
        assert energy._bin_index(37.9) == 11

    def test_high_temps_go_to_last_bin(self):
        """上限以上は最後のビンにまとめられる"""
        last = energy.TEMP_BIN_HIGH - energy.TEMP_BIN_LOW
        assert energy._bin_index(38.0) == last
        assert energy._bin_index(45.0) == last


class TestAnalyzeEnergySavings:
    """analyze_energy_savings のテスト"""

    def test_basic_savings(self):
        """散水あり/なしの電力差から削減量が推定される"""
        # 30℃ 台: 散水あり 800W、散水なし 1000W を各 6 サンプル（= 各 1 時間）
        samples = make_samples(30.5, power_on=800.0, power_off=1000.0, count=6)

        result = energy.analyze_energy_savings(
            samples,
            water_amount=100.0,
            water_cost=25.0,
            slot_hours=1 / 6,
            electricity_unit_price=31.0,
        )

        assert result.valid
        # 削減電力量: (1000 - 800) W × 6 サンプル × (1/6) h = 0.2 kWh
        assert result.saved_energy_kwh == pytest.approx(0.2)
        assert result.saved_cost == pytest.approx(0.2 * 31.0)
        assert result.water_cost == 25.0
        assert result.net_benefit == pytest.approx(0.2 * 31.0 - 25.0)
        assert result.watering_hours == pytest.approx(1.0)

    def test_multiple_bins_are_summed(self):
        """複数ビンの削減量が合算される"""
        samples = make_samples(30.5, power_on=800.0, power_off=1000.0, count=6) + make_samples(
            33.5, power_on=1000.0, power_off=1300.0, count=3
        )

        result = energy.analyze_energy_savings(samples, water_amount=0.0, water_cost=0.0, slot_hours=1 / 6)

        assert result.valid
        # 0.2 kWh + (300 W × 3 × 1/6 h) = 0.2 + 0.15 kWh
        assert result.saved_energy_kwh == pytest.approx(0.35)

    def test_bins_below_low_are_ignored(self):
        """下限未満の外気温は集計対象外"""
        samples = make_samples(20.0, power_on=500.0, power_off=900.0, count=10)

        result = energy.analyze_energy_savings(samples, water_amount=0.0, water_cost=0.0)

        assert not result.valid
        assert all(b.on_count == 0 and b.off_count == 0 for b in result.bins)

    def test_insufficient_samples_bin_is_not_compared(self):
        """サンプル数が最小数未満のビンは比較対象にならない"""
        # 散水ありのみ（対照群なし）
        samples = [energy.EnergySample(temperature=30.5, power=800.0, watering=True) for _ in range(10)]

        result = energy.analyze_energy_savings(samples, water_amount=0.0, water_cost=0.0)

        assert not result.valid
        assert "不足" in result.message

    def test_empty_samples(self):
        """サンプルが空でも落ちない"""
        result = energy.analyze_energy_savings([], water_amount=0.0, water_cost=0.0)

        assert not result.valid
        assert result.saved_energy_kwh == 0.0
        assert result.net_benefit == 0.0

    def test_negative_savings_are_kept(self):
        """散水ありの方が電力が大きい場合は負の削減量として扱う（クランプしない）"""
        samples = make_samples(30.5, power_on=1000.0, power_off=800.0, count=6)

        result = energy.analyze_energy_savings(samples, water_amount=0.0, water_cost=0.0, slot_hours=1 / 6)

        assert result.valid
        assert result.saved_energy_kwh == pytest.approx(-0.2)
        assert result.net_benefit < 0

    def test_chart_dict_structure(self):
        """チャート用のシリアライズ結果の構造"""
        samples = make_samples(30.5, power_on=800.0, power_off=1000.0, count=6)
        result = energy.analyze_energy_savings(samples, water_amount=0.0, water_cost=0.0)

        chart = result.to_chart_dict()
        bin_count = energy.TEMP_BIN_HIGH - energy.TEMP_BIN_LOW + 1
        assert chart["valid"] is True
        assert len(chart["labels"]) == bin_count
        assert len(chart["power_on"]) == bin_count
        assert len(chart["power_off"]) == bin_count
        # 30℃ 台のビン (index 4) に値が入り、他は None
        index = energy._bin_index(30.5)
        assert chart["power_on"][index] == pytest.approx(800.0)
        assert chart["power_off"][index] == pytest.approx(1000.0)
        assert chart["power_on"][0] is None
        assert chart["labels"][0] == "26〜27℃"
        assert chart["labels"][-1] == "38℃〜"

    def test_insufficient_analysis_helper(self):
        """insufficient_analysis はデータ不足の結果を返す"""
        result = energy.insufficient_analysis("テスト理由")
        assert not result.valid
        assert result.message == "テスト理由"
        assert result.to_chart_dict()["valid"] is False
