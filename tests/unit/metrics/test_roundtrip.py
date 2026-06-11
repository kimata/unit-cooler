#!/usr/bin/env python3
# ruff: noqa: S101
"""メトリクスの書き込み → 読み出しのラウンドトリップテスト

実 SQLite ファイルを使い、MetricsCollector で書き込んだデータが
page.py のデータ準備関数経由で正しく読み出せることを検証します。
"""

from __future__ import annotations

import contextlib
import datetime
import sqlite3
import zoneinfo

import unit_cooler.metrics.webapi.page as page
from unit_cooler.metrics.collector import MetricsCollector

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")


class FakeClock:
    """テスト用の時刻制御"""

    def __init__(self, start: datetime.datetime):
        self.current = start

    def now(self) -> datetime.datetime:
        return self.current

    def advance(self, **kwargs) -> None:
        self.current += datetime.timedelta(**kwargs)

    def jump(self, target: datetime.datetime) -> None:
        self.current = target


def write_test_data(collector: MetricsCollector, clock: FakeClock) -> None:
    """2 日にまたがるテストデータを書き込む"""
    # 6/15 の 3 時台に 5 分間のデータ
    for i in range(5):
        collector.update_cooling_mode(2)
        collector.update_duty_ratio(30.0, 60.0)
        collector.update_environmental_data(temperature=30.0 + i, humidity=60.0)
        clock.advance(minutes=1)

    # 6/17 の 15 時台に 3 分間のデータ
    clock.jump(datetime.datetime(2024, 6, 17, 15, 0, 0, tzinfo=TIMEZONE))
    for _ in range(3):
        collector.update_cooling_mode(1)
        collector.update_environmental_data(temperature=25.0)
        clock.advance(minutes=1)

    # cooling_mode のない行（相関ペアから除外される）
    collector.update_environmental_data(temperature=20.0)
    clock.advance(minutes=1)

    collector.record_valve_operation()
    collector.record_valve_operation()
    collector.record_error("test_error", "test message")
    collector.close()


class TestRoundtrip:
    """書き込み → 読み出しのラウンドトリップ"""

    @classmethod
    def setup_collector(cls, tmp_path) -> MetricsCollector:
        clock = FakeClock(datetime.datetime(2024, 6, 15, 3, 0, 0, tzinfo=TIMEZONE))
        collector = MetricsCollector(tmp_path / "metrics.db", time_func=clock.now)
        write_test_data(collector, clock)
        return collector

    def test_hourly_distribution_buckets(self, tmp_path):
        """時間別分布のバケットが正しい（ローカル時刻基準）"""
        collector = self.setup_collector(tmp_path)
        boxplot_data = page.prepare_boxplot_data(collector)

        # 3 時台: cooling_mode=2 が 5 件
        cooling = boxplot_data["boxplot_cooling_mode"]
        assert len(cooling) == 24
        assert cooling[3]["x"] == "03:00"
        assert cooling[3]["y"]["median"] == 2
        # 15 時台: cooling_mode=1
        assert cooling[15]["y"]["median"] == 1
        # データのない時間帯は 0
        assert cooling[0]["y"]["median"] == 0

        # Duty 比はパーセント表示（0.5 → 50.0）
        assert boxplot_data["boxplot_duty_ratio"][3]["y"]["median"] == 50.0

        # バルブ操作は 15 時台に 2 回
        assert boxplot_data["boxplot_valve_ops"][15]["y"]["median"] == 2

    def test_period_summary(self, tmp_path):
        """期間情報が正しく得られる"""
        collector = self.setup_collector(tmp_path)
        period = collector.get_period_summary()

        assert period.start == datetime.datetime(2024, 6, 15, 3, 0, 0, tzinfo=TIMEZONE)
        assert period.end is not None
        assert period.end.date() == datetime.date(2024, 6, 17)
        # データが存在する日数（6/15 と 6/17 の 2 日）
        assert period.total_days == 2

        # 期間テキストはデータ期間の幅（6/15〜6/17 の 3 日間）
        assert page.format_period_text(period) == "過去3日間（2024年06月15日〜）の冷却システム統計"

    def test_period_summary_empty(self, tmp_path):
        """データなしの場合の期間情報"""
        collector = MetricsCollector(tmp_path / "metrics.db")
        period = collector.get_period_summary()

        assert period.start is None
        assert period.end is None
        assert period.total_days == 0
        assert page.format_period_text(period) == "データなし"
        collector.close()

    def test_timeseries_is_ascending(self, tmp_path):
        """時系列データは古い順に並ぶ"""
        collector = self.setup_collector(tmp_path)
        timeseries = page.prepare_timeseries_data(collector.get_minute_data())

        assert timeseries[0]["timestamp"] == "06/15 03:00"
        assert timeseries[0]["cooling_mode"] == 2
        assert timeseries[0]["temperature"] == 30.0
        # 最後の行は 6/17 のデータ
        assert timeseries[-1]["timestamp"].startswith("06/17")

    def test_correlation_pairs_exclude_partial_rows(self, tmp_path):
        """相関ペアは両カラムが non-None の行のみ"""
        collector = self.setup_collector(tmp_path)
        correlation = page.prepare_correlation_data(collector.get_minute_data())

        # temperature と cooling_mode が両方あるのは 8 行
        # （temperature=20.0 の行は cooling_mode がないので除外）
        pair = correlation["temp_cooling"]
        assert len(pair["x"]) == len(pair["y"]) == 8
        assert 20.0 not in pair["x"]

        # duty_ratio は最初の 5 行のみ
        assert len(correlation["humidity_duty"]["x"]) == 5

        # lux は未記録なので空
        assert correlation["lux_duty"] == {"x": [], "y": []}

    def test_statistics(self, tmp_path):
        """統計情報が正しく得られる"""
        collector = self.setup_collector(tmp_path)
        minute_data = collector.get_minute_data()
        hourly_data = collector.get_hourly_data()
        period = collector.get_period_summary()

        assert collector.count_errors() == 1

        stats = page.generate_statistics(
            minute_data, hourly_data, collector.count_errors(), period.total_days
        )
        assert stats["data_points"] == 9
        assert stats["cooling_mode_avg"] == (2 * 5 + 1 * 3) / 8
        assert stats["duty_ratio_avg"] == 0.5
        assert stats["valve_operations_total"] == 2
        assert stats["error_total"] == 1
        assert stats["total_days"] == 2

        formatted = page.format_statistics(stats)
        assert formatted["duty_ratio_avg"] == "50.0%"
        assert formatted["data_points"] == "9"


class TestTimestampMigration:
    """旧形式タイムスタンプのマイグレーション"""

    def test_old_format_is_migrated_and_readable(self, tmp_path):
        """スペース区切りタイムスタンプが ISO 8601 に変換され読み出せる"""
        db_path = tmp_path / "metrics.db"

        # スキーマ作成のため一度初期化してから旧形式データを直接 INSERT する
        collector = MetricsCollector(db_path)
        resolved_path = collector.db_path
        collector.close()

        with contextlib.closing(sqlite3.connect(resolved_path)) as conn:
            conn.execute(
                "INSERT INTO minute_metrics (timestamp, cooling_mode, duty_ratio) VALUES (?, ?, ?)",
                ("2024-06-15 12:30:00+09:00", 2, 0.5),
            )
            conn.execute(
                "INSERT INTO hourly_metrics (timestamp, valve_operations) VALUES (?, ?)",
                ("2024-06-15 12:00:00+09:00", 3),
            )
            conn.commit()

        # 再初期化でマイグレーションが実行される
        collector = MetricsCollector(db_path)

        rows = collector.get_minute_data()
        assert rows[0]["timestamp"] == "2024-06-15T12:30:00+09:00"
        assert page.normalize_timestamp(rows[0]["timestamp"]) == datetime.datetime(
            2024, 6, 15, 12, 30, 0, tzinfo=TIMEZONE
        )

        # 時間別取得もローカル時刻基準で正しい
        assert collector.get_hourly_values("cooling_mode") == [(12, 2)]
        assert collector.get_hourly_values("valve_operations") == [(12, 3)]

        period = collector.get_period_summary()
        assert period.total_days == 1
        collector.close()
