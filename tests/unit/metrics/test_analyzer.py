#!/usr/bin/env python3
# ruff: noqa: S101
"""unit_cooler.metrics.analyzer のテスト"""

from __future__ import annotations

import datetime
import zoneinfo

import pytest

from unit_cooler.metrics.analyzer import MetricsAnalyzer, get_metrics_analyzer
from unit_cooler.metrics.collector import MetricsCollector

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")


class TestMetricsAnalyzerInit:
    """MetricsAnalyzer 初期化のテスト"""

    def test_init_with_collector(self, tmp_path):
        """collector を指定して初期化"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        assert analyzer.collector is collector
        collector.close()

    def test_init_requires_collector(self, tmp_path):
        """collector が必須である"""
        # MetricsAnalyzer は collector が必須引数になった
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # collector を渡さないと TypeError になる
        with pytest.raises(TypeError):
            MetricsAnalyzer()  # type: ignore[call-arg]

        collector.close()


class TestMetricsAnalyzerGetTimeseriesData:
    """get_timeseries_data のテスト"""

    @pytest.fixture
    def analyzer_with_data(self, tmp_path):
        """テストデータ入りの analyzer"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # テストデータを挿入
        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for i in range(10):
                timestamp = now - datetime.timedelta(minutes=i)
                conn.execute(
                    """
                    INSERT INTO minute_metrics
                    (timestamp, cooling_mode, duty_ratio, temperature, humidity)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (timestamp, i % 5, i * 0.1, 25 + i, 50 + i),
                )

            for i in range(5):
                timestamp = now - datetime.timedelta(hours=i)
                conn.execute(
                    """
                    INSERT INTO hourly_metrics (timestamp, valve_operations)
                    VALUES (?, ?)
                    """,
                    (timestamp, i * 5),
                )

        analyzer = MetricsAnalyzer(collector)
        yield analyzer
        collector.close()

    def test_get_timeseries_data_returns_dict(self, analyzer_with_data):
        """dict が返される"""
        result = analyzer_with_data.get_timeseries_data(days=1)

        assert "cooling_mode_timeseries" in result
        assert "duty_ratio_timeseries" in result
        assert "valve_operations_timeseries" in result

    def test_get_timeseries_data_cooling_mode(self, analyzer_with_data):
        """cooling_mode の時系列データ"""
        result = analyzer_with_data.get_timeseries_data(days=1)

        assert len(result["cooling_mode_timeseries"]) > 0
        for item in result["cooling_mode_timeseries"]:
            assert "timestamp" in item
            assert "value" in item

    def test_get_timeseries_data_valve_operations(self, analyzer_with_data):
        """valve_operations の時系列データ"""
        result = analyzer_with_data.get_timeseries_data(days=1)

        assert len(result["valve_operations_timeseries"]) > 0


class TestMetricsAnalyzerGetHourlyBoxplotData:
    """get_hourly_boxplot_data のテスト"""

    @pytest.fixture
    def analyzer_with_hourly_data(self, tmp_path):
        """時間別データ入りの analyzer"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # 各時間帯に複数のデータを挿入
        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for day in range(3):
                for hour in range(24):
                    for minute in range(0, 60, 10):
                        timestamp = now.replace(
                            hour=hour, minute=minute, second=0, microsecond=0
                        ) - datetime.timedelta(days=day)
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO minute_metrics
                            (timestamp, cooling_mode, duty_ratio)
                            VALUES (?, ?, ?)
                            """,
                            (timestamp, (hour % 5), hour * 0.04),
                        )

        analyzer = MetricsAnalyzer(collector)
        yield analyzer
        collector.close()

    def test_get_hourly_boxplot_data_returns_dict(self, analyzer_with_hourly_data):
        """dict が返される"""
        result = analyzer_with_hourly_data.get_hourly_boxplot_data(days=7)

        assert "cooling_mode_boxplot" in result
        assert "duty_ratio_boxplot" in result
        assert "valve_operations_boxplot" in result

    def test_get_hourly_boxplot_data_has_24_hours(self, analyzer_with_hourly_data):
        """24 時間分のデータがある"""
        result = analyzer_with_hourly_data.get_hourly_boxplot_data(days=7)

        # データがある時間のみ返される
        cooling_mode_data = result["cooling_mode_boxplot"]
        if cooling_mode_data:
            for item in cooling_mode_data:
                assert "hour" in item
                assert 0 <= item["hour"] < 24


class TestMetricsAnalyzerGetCorrelationAnalysis:
    """get_correlation_analysis のテスト"""

    @pytest.fixture
    def analyzer_with_env_data(self, tmp_path):
        """環境データ入りの analyzer"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # 相関分析用のデータを挿入
        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for i in range(100):
                timestamp = now - datetime.timedelta(minutes=i)
                # 温度と cooling_mode に相関を持たせる
                temp = 25 + i * 0.1
                cooling_mode = int(temp / 10)
                conn.execute(
                    """
                    INSERT INTO minute_metrics
                    (timestamp, cooling_mode, duty_ratio, temperature, humidity,
                     lux, solar_radiation, rain_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, cooling_mode, i * 0.01, temp, 50 + i * 0.1, 1000 + i * 10, 500 + i * 5, 0),
                )

        analyzer = MetricsAnalyzer(collector)
        yield analyzer
        collector.close()

    def test_get_correlation_analysis_returns_dict(self, analyzer_with_env_data):
        """dict が返される"""
        result = analyzer_with_env_data.get_correlation_analysis(days=1)

        assert "correlations" in result
        assert "scatter_data" in result

    def test_get_correlation_analysis_has_metrics(self, analyzer_with_env_data):
        """cooling_mode と duty_ratio の相関が含まれる"""
        result = analyzer_with_env_data.get_correlation_analysis(days=1)

        assert "cooling_mode" in result["correlations"]
        assert "duty_ratio" in result["correlations"]

    def test_get_correlation_analysis_has_env_factors(self, analyzer_with_env_data):
        """環境要因との相関が含まれる"""
        result = analyzer_with_env_data.get_correlation_analysis(days=1)

        correlations = result["correlations"]["cooling_mode"]
        assert "temperature" in correlations
        assert "humidity" in correlations


class TestMetricsAnalyzerGetSummaryStatistics:
    """get_summary_statistics のテスト"""

    @pytest.fixture
    def analyzer_with_stats_data(self, tmp_path):
        """統計データ入りの analyzer"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for i in range(50):
                timestamp = now - datetime.timedelta(minutes=i)
                conn.execute(
                    """
                    INSERT INTO minute_metrics
                    (timestamp, cooling_mode, duty_ratio, temperature)
                    VALUES (?, ?, ?, ?)
                    """,
                    (timestamp, i % 5, i * 0.02, 25 + i * 0.1),
                )

        analyzer = MetricsAnalyzer(collector)
        yield analyzer
        collector.close()

    def test_get_summary_statistics_returns_dict(self, analyzer_with_stats_data):
        """dict が返される"""
        result = analyzer_with_stats_data.get_summary_statistics(days=1)

        assert "period_days" in result
        assert "total_data_points" in result
        assert "cooling_mode" in result
        assert "environmental" in result

    def test_get_summary_statistics_column_stats(self, analyzer_with_stats_data):
        """各列の統計が含まれる"""
        result = analyzer_with_stats_data.get_summary_statistics(days=1)

        cooling_mode_stats = result["cooling_mode"]
        assert "count" in cooling_mode_stats
        assert "mean" in cooling_mode_stats
        assert "median" in cooling_mode_stats
        assert "std" in cooling_mode_stats
        assert "min" in cooling_mode_stats
        assert "max" in cooling_mode_stats


class TestMetricsAnalyzerPrivateMethods:
    """プライベートメソッドのテスト"""

    def test_calculate_hourly_boxplot_empty_df(self, tmp_path):
        """空の DataFrame の場合は空リスト"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        result = analyzer._calculate_hourly_boxplot(pd.DataFrame(), "cooling_mode")
        assert result == []

        collector.close()

    def test_calculate_hourly_boxplot_missing_column(self, tmp_path):
        """列が存在しない場合は空リスト"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        df = pd.DataFrame({"hour": [0, 1, 2], "other_column": [1, 2, 3]})
        result = analyzer._calculate_hourly_boxplot(df, "cooling_mode")
        assert result == []

        collector.close()

    def test_detect_outliers(self, tmp_path):
        """外れ値検出"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        # 外れ値を含むデータ
        data = pd.Series([1, 2, 3, 4, 5, 100])
        outliers = analyzer._detect_outliers(data)

        assert 100.0 in outliers

        collector.close()

    def test_get_column_stats_empty_df(self, tmp_path):
        """空の DataFrame の統計"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        result = analyzer._get_column_stats(pd.DataFrame(), "cooling_mode")
        assert result["count"] == 0
        assert result["mean"] is None

        collector.close()


class TestGetMetricsAnalyzer:
    """get_metrics_analyzer 関数のテスト"""

    def test_returns_analyzer_instance(self, tmp_path):
        """MetricsAnalyzer インスタンスが返される"""
        from unit_cooler.metrics import collector as collector_module

        # グローバル collector をリセット
        collector_module._metrics_collector = None

        db_path = tmp_path / "metrics.db"
        analyzer = get_metrics_analyzer(str(db_path))
        assert isinstance(analyzer, MetricsAnalyzer)

        # クリーンアップ
        collector_module._metrics_collector = None


class TestMetricsAnalyzerEdgeCases:
    """エッジケースのテスト"""

    def test_get_correlation_analysis_empty_data(self, tmp_path):
        """データがない場合のエラー"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        result = analyzer.get_correlation_analysis(days=1)

        assert "error" in result
        assert result["error"] == "No data available for correlation analysis"
        collector.close()

    def test_get_correlation_analysis_insufficient_data(self, tmp_path):
        """相関分析に必要なデータが不足している場合"""

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # 10件未満のデータを挿入
        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for i in range(5):  # 5件のみ
                timestamp = now - datetime.timedelta(minutes=i)
                conn.execute(
                    """
                    INSERT INTO minute_metrics
                    (timestamp, cooling_mode, temperature)
                    VALUES (?, ?, ?)
                    """,
                    (timestamp, i % 3, 25 + i),
                )

        analyzer = MetricsAnalyzer(collector)
        result = analyzer.get_correlation_analysis(days=1)

        # データ不足の場合、correlation は None になる
        assert "correlations" in result
        assert result["correlations"]["cooling_mode"]["temperature"]["correlation"] is None
        assert result["correlations"]["cooling_mode"]["temperature"]["sample_size"] == 5

        collector.close()

    def test_get_correlation_analysis_large_dataset_sampling(self, tmp_path):
        """1000件以上のデータがある場合のサンプリング"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # 1500件のデータを挿入
        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for i in range(1500):
                timestamp = now - datetime.timedelta(seconds=i)
                conn.execute(
                    """
                    INSERT INTO minute_metrics
                    (timestamp, cooling_mode, temperature)
                    VALUES (?, ?, ?)
                    """,
                    (timestamp, i % 5, 25 + (i % 10)),
                )

        analyzer = MetricsAnalyzer(collector)
        result = analyzer.get_correlation_analysis(days=1)

        # scatter_data は 1000 件にサンプリングされる
        scatter_count = len(result["scatter_data"]["cooling_mode"]["temperature"])
        assert scatter_count == 1000

        collector.close()

    def test_calculate_hourly_boxplot_all_null_column(self, tmp_path):
        """列が全て NULL の場合"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        df = pd.DataFrame(
            {
                "hour": [0, 1, 2],
                "cooling_mode": [None, None, None],
            }
        )
        result = analyzer._calculate_hourly_boxplot(df, "cooling_mode")

        # NULL を dropna した後に空になるため、空リストを返す
        assert result == []

        collector.close()

    def test_calculate_hourly_boxplot_hour_with_no_data(self, tmp_path):
        """特定の時間にデータがない場合"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        # hour 0 と 1 にのみデータがある
        df = pd.DataFrame(
            {
                "hour": [0, 0, 0, 1, 1, 1],
                "cooling_mode": [1, 2, 3, 4, 5, 6],
            }
        )
        result = analyzer._calculate_hourly_boxplot(df, "cooling_mode")

        # 24時間分のデータが返される（データがない時間は None）
        assert len(result) == 24
        # hour 0 はデータがある
        hour_0 = next(r for r in result if r["hour"] == 0)
        assert hour_0["count"] == 3
        # hour 2 はデータがない
        hour_2 = next(r for r in result if r["hour"] == 2)
        assert hour_2["count"] == 0
        assert hour_2["median"] is None

        collector.close()

    def test_get_column_stats_all_null_values(self, tmp_path):
        """列の値が全て NULL の場合"""
        import pandas as pd

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        analyzer = MetricsAnalyzer(collector)

        df = pd.DataFrame(
            {
                "cooling_mode": [None, None, None],
            }
        )
        result = analyzer._get_column_stats(df, "cooling_mode")

        assert result["count"] == 0
        assert result["mean"] is None
        assert result["median"] is None

        collector.close()

    def test_get_hourly_boxplot_data_with_no_minute_data(self, tmp_path):
        """分データがない場合"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # 時間データのみを挿入
        with collector._get_db_connection() as conn:
            now = datetime.datetime.now(TIMEZONE)
            for i in range(3):
                timestamp = now - datetime.timedelta(hours=i)
                conn.execute(
                    """
                    INSERT INTO hourly_metrics (timestamp, valve_operations)
                    VALUES (?, ?)
                    """,
                    (timestamp, i * 5),
                )

        analyzer = MetricsAnalyzer(collector)
        result = analyzer.get_hourly_boxplot_data(days=1)

        # 分データがないので cooling_mode と duty_ratio は空
        assert result["cooling_mode_boxplot"] == []
        assert result["duty_ratio_boxplot"] == []

        collector.close()
