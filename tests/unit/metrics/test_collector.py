#!/usr/bin/env python3
# ruff: noqa: S101, E731
"""unit_cooler.metrics.collector のテスト"""

from __future__ import annotations

import datetime
import zoneinfo

import pytest

from unit_cooler.metrics.collector import MetricsCollector

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")


class TestMetricsCollectorInit:
    """MetricsCollector 初期化のテスト"""

    def test_creates_database_file(self, tmp_path):
        """データベースファイルが作成される"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        assert db_path.exists()
        collector.close()

    def test_creates_parent_directory(self, tmp_path):
        """親ディレクトリが作成される"""
        db_path = tmp_path / "subdir" / "metrics.db"
        collector = MetricsCollector(db_path)

        assert db_path.parent.exists()
        collector.close()

    def test_custom_time_func(self, tmp_path):
        """カスタム時間関数が使用される"""
        fixed_time = datetime.datetime(2024, 6, 15, 12, 30, 0, tzinfo=TIMEZONE)
        time_func = lambda: fixed_time

        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path, time_func=time_func)

        assert collector._time_func() == fixed_time
        collector.close()


class TestMetricsCollectorUpdateMethods:
    """MetricsCollector の更新メソッドのテスト"""

    @pytest.fixture
    def collector(self, tmp_path):
        """一時 DB を使用する collector"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)
        yield collector
        collector.close()

    def test_update_cooling_mode(self, collector):
        """update_cooling_mode でデータが設定される"""
        collector.update_cooling_mode(3)
        assert collector._current_minute_data.get("cooling_mode") == 3

    def test_update_duty_ratio(self, collector):
        """update_duty_ratio でデータが設定される"""
        collector.update_duty_ratio(30.0, 60.0)
        assert collector._current_minute_data.get("duty_ratio") == 0.5

    def test_update_duty_ratio_zero_total(self, collector):
        """total_time が 0 の場合は設定されない"""
        collector.update_duty_ratio(30.0, 0.0)
        assert "duty_ratio" not in collector._current_minute_data

    def test_update_environmental_data_all_values(self, collector):
        """update_environmental_data で全ての値が設定される"""
        collector.update_environmental_data(
            temperature=30.5,
            humidity=60.0,
            lux=50000.0,
            solar_radiation=800.0,
            rain_amount=0.0,
        )
        assert collector._current_minute_data["temperature"] == 30.5
        assert collector._current_minute_data["humidity"] == 60.0
        assert collector._current_minute_data["lux"] == 50000.0
        assert collector._current_minute_data["solar_radiation"] == 800.0
        assert collector._current_minute_data["rain_amount"] == 0.0

    def test_update_environmental_data_partial(self, collector):
        """update_environmental_data で一部の値のみ設定"""
        collector.update_environmental_data(temperature=25.0)
        assert collector._current_minute_data["temperature"] == 25.0
        assert "humidity" not in collector._current_minute_data

    def test_update_flow_value(self, collector):
        """update_flow_value でデータが設定される"""
        collector.update_flow_value(2.5)
        assert collector._current_minute_data.get("flow_value") == 2.5

    def test_record_valve_operation(self, collector):
        """record_valve_operation でカウントが増加する"""
        assert collector._current_hour_data["valve_operations"] == 0
        collector.record_valve_operation()
        assert collector._current_hour_data["valve_operations"] == 1
        collector.record_valve_operation()
        assert collector._current_hour_data["valve_operations"] == 2


class TestMetricsCollectorMinuteBoundary:
    """分境界処理のテスト"""

    def test_minute_boundary_saves_data(self, tmp_path):
        """分境界を越えるとデータが保存される"""
        db_path = tmp_path / "metrics.db"

        # 時間を制御可能にする (mutableな参照を使用)
        current_time_holder = {"time": datetime.datetime(2024, 6, 15, 12, 30, 30, tzinfo=TIMEZONE)}
        time_func = lambda: current_time_holder["time"]

        collector = MetricsCollector(db_path, time_func=time_func)

        # 最初の更新（分境界を初期化）
        collector.update_cooling_mode(3)

        # 次の分に進める (分境界を越えるが、まだ新しいデータは入れない)
        current_time_holder["time"] = datetime.datetime(2024, 6, 15, 12, 31, 30, tzinfo=TIMEZONE)

        # 環境データで分境界チェックをトリガー（cooling_mode は変更しない）
        collector.update_environmental_data(temperature=25.0)

        # 以前のデータが保存されたことを確認
        data = collector.get_minute_data()
        assert len(data) == 1
        assert data[0]["cooling_mode"] == 3

        collector.close()

    def test_no_save_within_same_minute(self, tmp_path):
        """同じ分内では保存されない"""
        db_path = tmp_path / "metrics.db"

        current_time_holder = {"time": datetime.datetime(2024, 6, 15, 12, 30, 0, tzinfo=TIMEZONE)}
        time_func = lambda: current_time_holder["time"]

        collector = MetricsCollector(db_path, time_func=time_func)

        collector.update_cooling_mode(3)
        collector.update_cooling_mode(4)
        collector.update_cooling_mode(5)

        # まだ保存されていない
        data = collector.get_minute_data()
        assert len(data) == 0

        collector.close()


class TestMetricsCollectorHourBoundary:
    """時間境界処理のテスト"""

    def test_hour_boundary_saves_data(self, tmp_path):
        """時間境界を越えるとデータが保存される"""
        db_path = tmp_path / "metrics.db"

        # 時間を制御可能にする (mutableな参照を使用)
        current_time_holder = {"time": datetime.datetime(2024, 6, 15, 12, 59, 30, tzinfo=TIMEZONE)}
        time_func = lambda: current_time_holder["time"]

        collector = MetricsCollector(db_path, time_func=time_func)

        # バルブ操作を記録
        collector.record_valve_operation()
        collector.record_valve_operation()

        # 次の時間に進める
        current_time_holder["time"] = datetime.datetime(2024, 6, 15, 13, 0, 30, tzinfo=TIMEZONE)

        # 新しいバルブ操作（時間境界チェックをトリガー）
        collector.record_valve_operation()

        # データが保存されたことを確認
        # 注: 現在の実装では、境界をトリガーする操作も含めてカウントされる
        data = collector.get_hourly_data()
        assert len(data) == 1
        assert data[0]["valve_operations"] == 3

        collector.close()


class TestMetricsCollectorRecordError:
    """エラー記録のテスト"""

    def test_record_error(self, tmp_path):
        """エラーが記録される"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        collector.record_error("valve_error", "Valve failed to open")

        data = collector.get_error_data()
        assert len(data) == 1
        assert data[0]["error_type"] == "valve_error"
        assert data[0]["error_message"] == "Valve failed to open"

        collector.close()

    def test_record_error_without_message(self, tmp_path):
        """メッセージなしでエラーが記録される"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        collector.record_error("timeout_error")

        data = collector.get_error_data()
        assert len(data) == 1
        assert data[0]["error_type"] == "timeout_error"
        assert data[0]["error_message"] is None

        collector.close()


class TestMetricsCollectorGetData:
    """データ取得メソッドのテスト"""

    @pytest.fixture
    def collector_with_data(self, tmp_path):
        """テストデータが入った collector"""
        db_path = tmp_path / "metrics.db"
        collector = MetricsCollector(db_path)

        # 複数の分データを手動で挿入
        with collector._get_db_connection() as conn:
            for i in range(5):
                timestamp = datetime.datetime(2024, 6, 15, 12, i, 0, tzinfo=TIMEZONE)
                conn.execute(
                    """
                    INSERT INTO minute_metrics (timestamp, cooling_mode, duty_ratio)
                    VALUES (?, ?, ?)
                    """,
                    (timestamp, i, i * 0.1),
                )

            for i in range(3):
                timestamp = datetime.datetime(2024, 6, 15, i, 0, 0, tzinfo=TIMEZONE)
                conn.execute(
                    """
                    INSERT INTO hourly_metrics (timestamp, valve_operations)
                    VALUES (?, ?)
                    """,
                    (timestamp, i * 10),
                )

        yield collector
        collector.close()

    def test_get_minute_data_all(self, collector_with_data):
        """全ての分データを取得"""
        data = collector_with_data.get_minute_data()
        assert len(data) == 5

    def test_get_minute_data_with_limit(self, collector_with_data):
        """limit 付きで分データを取得"""
        data = collector_with_data.get_minute_data(limit=2)
        assert len(data) == 2

    def test_get_minute_data_with_time_range(self, collector_with_data):
        """時間範囲指定で分データを取得"""
        start = datetime.datetime(2024, 6, 15, 12, 1, 0, tzinfo=TIMEZONE)
        end = datetime.datetime(2024, 6, 15, 12, 3, 0, tzinfo=TIMEZONE)
        data = collector_with_data.get_minute_data(start_time=start, end_time=end)
        assert len(data) == 3

    def test_get_hourly_data_all(self, collector_with_data):
        """全ての時間データを取得"""
        data = collector_with_data.get_hourly_data()
        assert len(data) == 3

    def test_get_hourly_data_with_limit(self, collector_with_data):
        """limit 付きで時間データを取得"""
        data = collector_with_data.get_hourly_data(limit=1)
        assert len(data) == 1

    def test_get_error_data_empty(self, collector_with_data):
        """エラーがない場合は空リスト"""
        data = collector_with_data.get_error_data()
        assert len(data) == 0


class TestMetricsCollectorClose:
    """close メソッドのテスト"""

    def test_close_saves_pending_minute_data(self, tmp_path):
        """close 時に未保存の分データが保存される"""
        db_path = tmp_path / "metrics.db"

        current_time = datetime.datetime(2024, 6, 15, 12, 30, 30, tzinfo=TIMEZONE)
        collector = MetricsCollector(db_path, time_func=lambda: current_time)

        # 分境界を初期化
        collector.update_cooling_mode(5)

        # close で保存
        collector.close()

        # 新しい collector で確認
        collector2 = MetricsCollector(db_path)
        data = collector2.get_minute_data()
        assert len(data) == 1
        assert data[0]["cooling_mode"] == 5
        collector2.close()

    def test_close_saves_pending_hour_data(self, tmp_path):
        """close 時に未保存の時間データが保存される"""
        db_path = tmp_path / "metrics.db"

        current_time = datetime.datetime(2024, 6, 15, 12, 30, 30, tzinfo=TIMEZONE)
        collector = MetricsCollector(db_path, time_func=lambda: current_time)

        # 時間境界を初期化
        collector.record_valve_operation()
        collector.record_valve_operation()
        collector.record_valve_operation()

        # close で保存
        collector.close()

        # 新しい collector で確認
        collector2 = MetricsCollector(db_path)
        data = collector2.get_hourly_data()
        assert len(data) == 1
        assert data[0]["valve_operations"] == 3
        collector2.close()


class TestGetMetricsCollector:
    """get_metrics_collector 関数のテスト"""

    def test_returns_singleton(self, tmp_path, mocker):
        """シングルトンインスタンスが返される"""
        from unit_cooler.metrics import collector as collector_module

        # グローバル変数をリセット
        collector_module._metrics_collector = None

        db_path = tmp_path / "metrics.db"
        instance1 = collector_module.get_metrics_collector(db_path)
        instance2 = collector_module.get_metrics_collector(db_path)

        assert instance1 is instance2

        # クリーンアップ
        instance1.close()
        collector_module._metrics_collector = None
