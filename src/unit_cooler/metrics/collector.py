"""
New metrics collection system for outdoor unit cooler.

Collects:
- 1分毎の cooling_mode の値
- 1分毎の Duty 比 (ON と ON+OFF の比率)
- 1分毎の 気温、照度、日射量、降水量、湿度
- 1時間あたりのバルブ操作回数
- ON している際の流量
- エラー発生
"""

import datetime
import logging
import pathlib
import sqlite3
import threading
import zoneinfo
from collections.abc import Callable
from contextlib import contextmanager

import my_lib.sqlite_util

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")
DEFAULT_DB_PATH = pathlib.Path("data/metrics.db")
SCHEMA_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "schema" / "sqlite.schema"

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Metrics collection system focused on cooling mode analysis."""

    def __init__(
        self,
        db_path: str | pathlib.Path = DEFAULT_DB_PATH,
        time_func: Callable[[], datetime.datetime] | None = None,
    ):
        """Initialize MetricsCollector with database path.

        Args:
            db_path: Path to the SQLite database file.
            time_func: Optional function that returns current datetime.
                       Defaults to datetime.datetime.now(TIMEZONE).
                       Used for testing time-dependent behavior.
        """
        self.db_path = pathlib.Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        self._lock = threading.Lock()
        self._time_func = time_func or (lambda: datetime.datetime.now(TIMEZONE))

        # Current state tracking
        self._current_minute_data: dict = {}
        self._current_hour_data: dict = {"valve_operations": 0}
        self._last_minute: datetime.datetime | None = None
        self._last_hour: datetime.datetime | None = None

    def _init_database(self):
        """Initialize database tables from schema file."""
        with self._get_db_connection() as conn:
            # WALモードを設定（分散ストレージに適している）
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA wal_autocheckpoint=100")

            # スキーマファイルからテーブルとインデックスを作成
            schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
            conn.executescript(schema_sql)

    @contextmanager
    def _get_db_connection(self):
        """Get database connection with proper error handling."""
        try:
            with my_lib.sqlite_util.connect(self.db_path, timeout=30.0) as conn:
                conn.row_factory = sqlite3.Row
                yield conn
                conn.commit()
        except Exception:
            logger.exception("Database error")
            raise

    def update_cooling_mode(self, cooling_mode: int):
        """Update current cooling mode value."""
        with self._lock:
            self._current_minute_data["cooling_mode"] = cooling_mode
            self._check_minute_boundary()

    def update_duty_ratio(self, on_time: float, total_time: float):
        """Update duty ratio (ON time / total time)."""
        with self._lock:
            if total_time > 0:
                self._current_minute_data["duty_ratio"] = on_time / total_time
            self._check_minute_boundary()

    def update_environmental_data(
        self,
        temperature: float | None = None,
        humidity: float | None = None,
        lux: float | None = None,
        solar_radiation: float | None = None,
        rain_amount: float | None = None,
    ):
        """Update environmental sensor data."""
        with self._lock:
            if temperature is not None:
                self._current_minute_data["temperature"] = temperature
            if humidity is not None:
                self._current_minute_data["humidity"] = humidity
            if lux is not None:
                self._current_minute_data["lux"] = lux
            if solar_radiation is not None:
                self._current_minute_data["solar_radiation"] = solar_radiation
            if rain_amount is not None:
                self._current_minute_data["rain_amount"] = rain_amount
            self._check_minute_boundary()

    def update_flow_value(self, flow_value: float):
        """Update flow value when valve is ON."""
        with self._lock:
            self._current_minute_data["flow_value"] = flow_value
            self._check_minute_boundary()

    def record_valve_operation(self):
        """Record a valve operation for hourly counting."""
        with self._lock:
            self._current_hour_data["valve_operations"] += 1
            self._check_hour_boundary()

    def record_error(self, error_type: str, error_message: str | None = None):
        """Record an error event."""
        now = self._time_func()

        try:
            with self._get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO error_events (timestamp, error_type, error_message)
                    VALUES (?, ?, ?)
                """,
                    (now, error_type, error_message),
                )
                logger.info("Recorded error: %s", error_type)
        except Exception:
            logger.exception("Failed to record error")

    def _check_minute_boundary(self):
        """Check if we crossed a minute boundary and save data."""
        now = self._time_func()
        current_minute = now.replace(second=0, microsecond=0)

        if self._last_minute is None:
            self._last_minute = current_minute
            return

        if current_minute > self._last_minute:
            self._save_minute_data(self._last_minute)
            self._current_minute_data = {}
            self._last_minute = current_minute

    def _check_hour_boundary(self):
        """Check if we crossed an hour boundary and save data."""
        now = self._time_func()
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        if self._last_hour is None:
            self._last_hour = current_hour
            return

        if current_hour > self._last_hour:
            self._save_hour_data(self._last_hour)
            self._current_hour_data = {"valve_operations": 0}
            self._last_hour = current_hour

    def _save_minute_data(self, timestamp: datetime.datetime):
        """Save accumulated minute data to database."""
        if not self._current_minute_data:
            logger.debug("No current minute data to save for %s", timestamp)
            return

        try:
            data = (
                timestamp,
                self._current_minute_data.get("cooling_mode"),
                self._current_minute_data.get("duty_ratio"),
                self._current_minute_data.get("temperature"),
                self._current_minute_data.get("humidity"),
                self._current_minute_data.get("lux"),
                self._current_minute_data.get("solar_radiation"),
                self._current_minute_data.get("rain_amount"),
                self._current_minute_data.get("flow_value"),
            )
            logger.info("Saving minute metrics for %s: %s", timestamp, self._current_minute_data)

            with self._get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO minute_metrics
                    (timestamp, cooling_mode, duty_ratio, temperature, humidity,
                     lux, solar_radiation, rain_amount, flow_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    data,
                )
                logger.info("Successfully saved minute metrics for %s", timestamp)
        except Exception:
            logger.exception("Failed to save minute data")

    def _save_hour_data(self, timestamp: datetime.datetime):
        """Save accumulated hour data to database."""
        try:
            with self._get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO hourly_metrics
                    (timestamp, valve_operations)
                    VALUES (?, ?)
                """,
                    (timestamp, self._current_hour_data["valve_operations"]),
                )
                logger.debug("Saved hourly metrics for %s", timestamp)
        except Exception:
            logger.exception("Failed to save hour data")

    def get_minute_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list:
        """Get minute-level metrics data."""
        with self._get_db_connection() as conn:
            query = "SELECT * FROM minute_metrics"
            params: list[datetime.datetime | int] = []

            if start_time or end_time:
                query += " WHERE"
                conditions = []
                if start_time:
                    conditions.append(" timestamp >= ?")
                    params.append(start_time)
                if end_time:
                    conditions.append(" timestamp <= ?")
                    params.append(end_time)
                query += " AND".join(conditions)

            query += " ORDER BY timestamp DESC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_hourly_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list:
        """Get hourly-level metrics data."""
        with self._get_db_connection() as conn:
            query = "SELECT * FROM hourly_metrics"
            params: list[datetime.datetime | int] = []

            if start_time or end_time:
                query += " WHERE"
                conditions = []
                if start_time:
                    conditions.append(" timestamp >= ?")
                    params.append(start_time)
                if end_time:
                    conditions.append(" timestamp <= ?")
                    params.append(end_time)
                query += " AND".join(conditions)

            query += " ORDER BY timestamp DESC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_error_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list:
        """Get error events data."""
        with self._get_db_connection() as conn:
            query = "SELECT * FROM error_events"
            params: list[datetime.datetime | int] = []

            if start_time or end_time:
                query += " WHERE"
                conditions = []
                if start_time:
                    conditions.append(" timestamp >= ?")
                    params.append(start_time)
                if end_time:
                    conditions.append(" timestamp <= ?")
                    params.append(end_time)
                query += " AND".join(conditions)

            query += " ORDER BY timestamp DESC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def close(self):
        """Clean shutdown of metrics collector."""
        with self._lock:
            # 最後のデータを保存
            now = self._time_func()
            current_minute = now.replace(second=0, microsecond=0)
            if self._current_minute_data:
                self._save_minute_data(current_minute)

            current_hour = now.replace(minute=0, second=0, microsecond=0)
            if self._current_hour_data.get("valve_operations", 0) > 0:
                self._save_hour_data(current_hour)

            # WALチェックポイントを実行
            try:
                with my_lib.sqlite_util.connect(self.db_path, timeout=30.0) as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.info("Metrics database closed cleanly")
            except Exception:
                logger.exception("Failed to checkpoint WAL")


# Global instance
_metrics_collector = None


def get_metrics_collector(db_path: str | pathlib.Path = DEFAULT_DB_PATH) -> MetricsCollector:
    """Get global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(db_path)
    return _metrics_collector
