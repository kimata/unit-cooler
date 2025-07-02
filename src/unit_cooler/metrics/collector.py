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
from contextlib import contextmanager

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")
DEFAULT_DB_PATH = pathlib.Path("data/metrics.db")

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Metrics collection system focused on cooling mode analysis."""  # noqa: D203

    def __init__(self, db_path: str | pathlib.Path = DEFAULT_DB_PATH):
        """Initialize MetricsCollector with database path."""
        self.db_path = pathlib.Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        self._lock = threading.Lock()

        # Current state tracking
        self._current_minute_data = {}
        self._current_hour_data = {"valve_operations": 0}
        self._last_minute = None
        self._last_hour = None

    def _init_database(self):
        """Initialize database tables for new metrics schema."""
        with self._get_db_connection() as conn:
            # 1分毎のメトリクス
            conn.execute("""
                CREATE TABLE IF NOT EXISTS minute_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    cooling_mode INTEGER,
                    duty_ratio REAL,
                    temperature REAL,
                    humidity REAL,
                    lux REAL,
                    solar_radiation REAL,
                    rain_amount REAL,
                    flow_value REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(timestamp)
                )
            """)

            # 1時間毎のメトリクス
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hourly_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    valve_operations INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(timestamp)
                )
            """)

            # エラー記録
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # インデックス作成
            conn.execute("CREATE INDEX IF NOT EXISTS idx_minute_timestamp ON minute_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hourly_timestamp ON hourly_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_error_timestamp ON error_events(timestamp)")

    @contextmanager
    def _get_db_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            logger.exception("Database error")
            raise
        finally:
            if conn:
                conn.close()

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
        now = datetime.datetime.now(TIMEZONE)

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
        now = datetime.datetime.now(TIMEZONE)
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
        now = datetime.datetime.now(TIMEZONE)
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
        limit: int = 1000,
    ) -> list:
        """Get minute-level metrics data."""
        with self._get_db_connection() as conn:
            query = "SELECT * FROM minute_metrics"
            params = []

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

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_hourly_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int = 168,
    ) -> list:  # 1週間分
        """Get hourly-level metrics data."""
        with self._get_db_connection() as conn:
            query = "SELECT * FROM hourly_metrics"
            params = []

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

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_error_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int = 100,
    ) -> list:
        """Get error events data."""
        with self._get_db_connection() as conn:
            query = "SELECT * FROM error_events"
            params = []

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

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]


# Global instance
_metrics_collector = None


def get_metrics_collector(db_path: str | pathlib.Path = DEFAULT_DB_PATH) -> MetricsCollector:
    """Get global metrics collector instance."""
    global _metrics_collector  # noqa: PLW0603
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(db_path)
    return _metrics_collector
