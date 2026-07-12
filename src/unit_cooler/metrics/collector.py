"""
New metrics collection system for outdoor unit cooler.

Collects:
- 1分毎の cooling_mode の値
- 1分毎の Duty 比 (ON と ON+OFF の比率)
- 1分毎の 気温、照度、日射量、湿度
- 1時間あたりのバルブ操作回数
- ON している際の流量
- エラー発生
"""

import datetime
import logging
import pathlib
import sqlite3
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

import my_lib.pytest_util
import my_lib.sqlite_util
import my_lib.time

# NOTE: スキーマパスはモジュール相対パスで解決しています。
# MetricsCollector は config が渡される前に初期化される場合があるため、
# config.base_dir を使用せず __file__ から解決しています。
# 将来的に初期化パターンを変更する場合は config.base_dir への移行を検討してください。
SCHEMA_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "schema" / "sqlite.schema"

logger = logging.getLogger(__name__)

# get_hourly_values で許可するカラムと対応テーブル（SQL インジェクション防止のホワイトリスト）
_HOURLY_VALUE_TABLES = {
    "cooling_mode": "minute_metrics",
    "duty_ratio": "minute_metrics",
    "valve_operations": "hourly_metrics",
}

# minute_metrics のうち集計クエリで参照を許可するカラム（SQL インジェクション防止のホワイトリスト）
_MINUTE_METRIC_COLUMNS = (
    "cooling_mode",
    "duty_ratio",
    "temperature",
    "humidity",
    "lux",
    "solar_radiation",
)


@dataclass(frozen=True)
class PeriodSummary:
    """データ収集期間のサマリー"""

    start: datetime.datetime | None
    end: datetime.datetime | None
    total_days: int  # データが存在する日数（重複なし）


@dataclass(frozen=True)
class StatisticsSummary:
    """基本統計のサマリー（SQL 側で集計した結果）"""

    cooling_mode_avg: float | None
    duty_ratio_avg: float | None
    valve_operations_total: int
    data_points: int


class MetricsCollector:
    """Metrics collection system focused on cooling mode analysis."""

    def __init__(
        self,
        db_path: str | pathlib.Path,
        time_func: Callable[[], datetime.datetime] | None = None,
    ):
        """Initialize MetricsCollector with database path.

        Args:
            db_path: Path to the SQLite database file.
            time_func: Optional function that returns current datetime.
                       Defaults to my_lib.time.now().
                       Used for testing time-dependent behavior.
        """
        # pytest-xdist 並列実行時にワーカー間で DB が共有されないようにする
        # (PYTEST_XDIST_WORKER が未設定の本番では元のパスが返る)
        self.db_path = my_lib.pytest_util.get_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        self._lock = threading.Lock()
        self._time_func = time_func or my_lib.time.now

        # Current state tracking
        self._current_minute_data: dict[str, float | int | None] = {}
        self._current_hour_data: dict[str, int] = {"valve_operations": 0}
        self._last_minute: datetime.datetime | None = None
        self._last_hour: datetime.datetime | None = None

    def _init_database(self) -> None:
        """Initialize database tables from schema file."""
        with self._get_db_connection() as conn:
            # WALモードを設定（分散ストレージに適している）
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA wal_autocheckpoint=100")

            # スキーマファイルからテーブルとインデックスを作成
            my_lib.sqlite_util.exec_schema_from_file(conn, SCHEMA_PATH)

            self._migrate_timestamps(conn)

    @staticmethod
    def _migrate_timestamps(conn: sqlite3.Connection) -> None:
        """旧形式タイムスタンプの 1 回限りのマイグレーション

        以前は sqlite3 のデフォルトアダプタ経由でスペース区切り
        ("2026-06-15 12:30:00+09:00") で保存されていたため、
        ISO 8601 (T 区切り) に変換する。

        NOTE: 旧形式と新形式の行が同一時刻で共存している場合、UPDATE が
        UNIQUE(timestamp) 違反になり初期化ごと失敗してしまうため、
        UPDATE OR IGNORE で変換できる行のみ変換し、衝突で残った旧形式行
        （変換済みの行と同時刻の重複データ）は削除する。
        """
        for table in ("minute_metrics", "hourly_metrics", "error_events"):
            cursor = conn.execute(
                f"UPDATE OR IGNORE {table} SET timestamp = REPLACE(timestamp, ' ', 'T') "  # noqa: S608
                "WHERE timestamp LIKE '% %'"
            )
            if cursor.rowcount > 0:
                logger.info("Migrated %d timestamps in %s to ISO 8601", cursor.rowcount, table)

            cursor = conn.execute(f"DELETE FROM {table} WHERE timestamp LIKE '% %'")  # noqa: S608
            if cursor.rowcount > 0:
                logger.warning(
                    "Removed %d old-format rows in %s that conflicted with migrated rows",
                    cursor.rowcount,
                    table,
                )

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

    def update_cooling_mode(self, cooling_mode: int) -> None:
        """Update current cooling mode value."""
        with self._lock:
            # NOTE: 境界チェックは状態更新の前に行う。後に行うと、新しい期間の
            # 最初の値が前の期間のタイムスタンプで保存されてしまう
            self._check_minute_boundary()
            self._current_minute_data["cooling_mode"] = cooling_mode

    def update_duty_ratio(self, on_time: float, total_time: float) -> None:
        """Update duty ratio (ON time / total time)."""
        with self._lock:
            self._check_minute_boundary()
            if total_time > 0:
                self._current_minute_data["duty_ratio"] = on_time / total_time

    def update_environmental_data(
        self,
        temperature: float | None = None,
        humidity: float | None = None,
        lux: float | None = None,
        solar_radiation: float | None = None,
    ) -> None:
        """Update environmental sensor data."""
        with self._lock:
            self._check_minute_boundary()
            if temperature is not None:
                self._current_minute_data["temperature"] = temperature
            if humidity is not None:
                self._current_minute_data["humidity"] = humidity
            if lux is not None:
                self._current_minute_data["lux"] = lux
            if solar_radiation is not None:
                self._current_minute_data["solar_radiation"] = solar_radiation

    def update_flow_value(self, flow_value: float) -> None:
        """Update flow value when valve is ON."""
        with self._lock:
            self._check_minute_boundary()
            self._current_minute_data["flow_value"] = flow_value

    def record_valve_operation(self) -> None:
        """Record a valve operation for hourly counting."""
        with self._lock:
            self._check_hour_boundary()
            self._current_hour_data["valve_operations"] += 1

    def record_error(self, error_type: str, error_message: str | None = None) -> None:
        """Record an error event."""
        now = self._time_func()

        try:
            with self._get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO error_events (timestamp, error_type, error_message)
                    VALUES (?, ?, ?)
                """,
                    (now.isoformat(), error_type, error_message),
                )
                logger.info("Recorded error: %s", error_type)
        except Exception:
            logger.exception("Failed to record error")

    def _check_minute_boundary(self) -> None:
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

    def _check_hour_boundary(self) -> None:
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

    def _save_minute_data(self, timestamp: datetime.datetime) -> None:
        """Save accumulated minute data to database."""
        if not self._current_minute_data:
            logger.debug("No current minute data to save for %s", timestamp)
            return

        try:
            data = (
                timestamp.isoformat(),
                self._current_minute_data.get("cooling_mode"),
                self._current_minute_data.get("duty_ratio"),
                self._current_minute_data.get("temperature"),
                self._current_minute_data.get("humidity"),
                self._current_minute_data.get("lux"),
                self._current_minute_data.get("solar_radiation"),
                self._current_minute_data.get("flow_value"),
            )
            logger.info("Saving minute metrics for %s: %s", timestamp, self._current_minute_data)

            with self._get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO minute_metrics
                    (timestamp, cooling_mode, duty_ratio, temperature, humidity,
                     lux, solar_radiation, flow_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    data,
                )
                logger.info("Successfully saved minute metrics for %s", timestamp)
        except Exception:
            logger.exception("Failed to save minute data")

    def _save_hour_data(self, timestamp: datetime.datetime) -> None:
        """Save accumulated hour data to database."""
        try:
            with self._get_db_connection() as conn:
                # NOTE: INSERT OR REPLACE だと、同一時間帯に再起動した際に再起動前のカウントを
                # 上書きして失ってしまう。加算 UPSERT にして既存値に積み増す (BUG #19)。
                conn.execute(
                    """
                    INSERT INTO hourly_metrics (timestamp, valve_operations)
                    VALUES (?, ?)
                    ON CONFLICT(timestamp) DO UPDATE SET
                        valve_operations = valve_operations + excluded.valve_operations
                """,
                    (timestamp.isoformat(), self._current_hour_data["valve_operations"]),
                )
                logger.debug("Saved hourly metrics for %s", timestamp)
        except Exception:
            logger.exception("Failed to save hour data")

    def _query(
        self,
        table: str,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """テーブルから期間・件数を指定してレコードを取得する"""
        with self._get_db_connection() as conn:
            query = f"SELECT * FROM {table}"  # noqa: S608  # table はクラス内の固定値のみ
            params: list[str | int] = []

            if start_time or end_time:
                query += " WHERE"
                conditions = []
                if start_time:
                    conditions.append(" timestamp >= ?")
                    params.append(start_time.isoformat())
                if end_time:
                    conditions.append(" timestamp <= ?")
                    params.append(end_time.isoformat())
                query += " AND".join(conditions)

            query += " ORDER BY timestamp DESC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)

            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_minute_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Get minute-level metrics data."""
        return self._query("minute_metrics", start_time, end_time, limit)

    def get_hourly_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Get hourly-level metrics data."""
        return self._query("hourly_metrics", start_time, end_time, limit)

    def get_error_data(
        self,
        start_time: datetime.datetime | None = None,
        end_time: datetime.datetime | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Get error events data."""
        return self._query("error_events", start_time, end_time, limit)

    def get_hourly_values(self, column: str) -> list[tuple[int, float]]:
        """時間帯 (0-23) と値のペアを全件取得する

        Note:
            strftime('%H', ...) はタイムゾーン付き ISO 8601 を UTC に変換してしまうため、
            ローカル時刻の時間を保持するよう substr で抽出している。
        """
        table = _HOURLY_VALUE_TABLES.get(column)
        if table is None:
            raise ValueError(f"Unsupported column: {column}")

        with self._get_db_connection() as conn:
            rows = conn.execute(
                f"SELECT CAST(substr(timestamp, 12, 2) AS INTEGER) AS hour, {column} AS value "  # noqa: S608
                f"FROM {table} WHERE {column} IS NOT NULL"
            ).fetchall()
            return [(row["hour"], row["value"]) for row in rows]

    def get_statistics_summary(self) -> StatisticsSummary:
        """基本統計（平均値・件数）を SQL 側で集計して取得する"""
        with self._get_db_connection() as conn:
            row = conn.execute(
                "SELECT AVG(cooling_mode), AVG(duty_ratio), COUNT(*) FROM minute_metrics"
            ).fetchone()
            valve_total = conn.execute(
                "SELECT COALESCE(SUM(valve_operations), 0) FROM hourly_metrics"
            ).fetchone()[0]

        return StatisticsSummary(
            cooling_mode_avg=row[0],
            duty_ratio_avg=row[1],
            valve_operations_total=valve_total,
            data_points=row[2],
        )

    def get_timeseries_data(self, max_points: int, target_points: int) -> list[dict]:
        """時系列チャート用に直近 max_points 分のデータを SQL 側で平均化して取得する（古い順）

        件数が target_points を超える場合は、行番号ベースのチャンク
        （chunk_size = 件数 // target_points）ごとに AVG で平均化し、
        各チャンクの先頭タイムスタンプを代表値として返す。
        """
        columns = ", ".join(_MINUTE_METRIC_COLUMNS)

        with self._get_db_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM (SELECT 1 FROM minute_metrics LIMIT ?)", (max_points,)
            ).fetchone()[0]

            if count <= target_points:
                rows = conn.execute(
                    f"SELECT timestamp, {columns} FROM "  # noqa: S608
                    "(SELECT * FROM minute_metrics ORDER BY timestamp DESC LIMIT ?) "
                    "ORDER BY timestamp ASC",
                    (max_points,),
                ).fetchall()
                return [dict(row) for row in rows]

            chunk_size = count // target_points
            averages = ", ".join(f"AVG({column}) AS {column}" for column in _MINUTE_METRIC_COLUMNS)
            rows = conn.execute(
                f"""
                WITH recent AS (
                    SELECT timestamp, {columns}
                    FROM minute_metrics ORDER BY timestamp DESC LIMIT ?
                ),
                numbered AS (
                    SELECT *, (ROW_NUMBER() OVER (ORDER BY timestamp ASC) - 1) / ? AS chunk
                    FROM recent
                )
                SELECT MIN(timestamp) AS timestamp, {averages}
                FROM numbered GROUP BY chunk ORDER BY chunk
                """,  # noqa: S608
                (max_points, chunk_size),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_correlation_pairs(self, x_column: str, y_column: str) -> tuple[list[float], list[float]]:
        """両カラムが non-NULL の行の (x, y) 値リストを取得する（新しい順）"""
        for column in (x_column, y_column):
            if column not in _MINUTE_METRIC_COLUMNS:
                raise ValueError(f"Unsupported column: {column}")

        with self._get_db_connection() as conn:
            rows = conn.execute(
                f"SELECT {x_column}, {y_column} FROM minute_metrics "  # noqa: S608
                f"WHERE {x_column} IS NOT NULL AND {y_column} IS NOT NULL "
                "ORDER BY timestamp DESC"
            ).fetchall()

        return [row[0] for row in rows], [row[1] for row in rows]

    def get_duty_by_bucket(self, start_time: datetime.datetime, bucket_minutes: int = 10) -> dict[str, float]:
        """10 分バケットごとの平均 Duty 比を取得する

        キーはローカル時刻 ISO 8601 の先頭 15 文字（"YYYY-MM-DDTHH:M"）で、
        分の 10 の位までを含むため 10 分単位のバケットになる。
        duty_ratio が NULL の行は 0（散水なし）として扱う。
        """
        if bucket_minutes != 10:
            raise ValueError("Only 10-minute buckets are supported")

        with self._get_db_connection() as conn:
            rows = conn.execute(
                "SELECT substr(timestamp, 1, 15) AS bucket, AVG(COALESCE(duty_ratio, 0)) AS duty "
                "FROM minute_metrics WHERE timestamp >= ? GROUP BY bucket",
                (start_time.isoformat(),),
            ).fetchall()

        return {row["bucket"]: row["duty"] for row in rows}

    def count_errors(self) -> int:
        """エラーイベントの総数を取得する"""
        with self._get_db_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM error_events").fetchone()[0]

    def get_period_summary(self) -> PeriodSummary:
        """データ収集期間（開始・終了・日数）を取得する

        Note:
            date(timestamp) はタイムゾーン付き ISO 8601 を UTC に変換してしまうため、
            ローカル日付を保持するよう substr で日付部分を抽出している。
        """
        with self._get_db_connection() as conn:
            row = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT substr(timestamp, 1, 10)) "
                "FROM (SELECT timestamp FROM minute_metrics UNION ALL SELECT timestamp FROM hourly_metrics)"
            ).fetchone()

        if row[0] is None:
            return PeriodSummary(start=None, end=None, total_days=0)

        return PeriodSummary(
            start=datetime.datetime.fromisoformat(row[0]),
            end=datetime.datetime.fromisoformat(row[1]),
            total_days=row[2],
        )

    def close(self) -> None:
        """Clean shutdown of metrics collector."""
        with self._lock:
            # NOTE: 最後のデータは「現在時刻の期間」ではなく「データが属する期間」
            # (_last_minute / _last_hour) に保存する。現在時刻を使うと、長時間
            # アイドル後の終了時に数時間先のバケットへ記帳されてしまう (BUG #17 と同型)。
            if self._current_minute_data and self._last_minute is not None:
                self._save_minute_data(self._last_minute)

            if self._current_hour_data.get("valve_operations", 0) > 0 and self._last_hour is not None:
                self._save_hour_data(self._last_hour)

            # WALチェックポイントを実行
            try:
                with my_lib.sqlite_util.connect(self.db_path, timeout=30.0) as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.info("Metrics database closed cleanly")
            except Exception:
                logger.exception("Failed to checkpoint WAL")


# Global instance
_metrics_collector: MetricsCollector | None = None
_metrics_collector_lock = threading.Lock()


def get_metrics_collector(db_path: str | pathlib.Path | None = None) -> MetricsCollector:
    """Get global metrics collector instance.

    Args:
        db_path: Path to the SQLite database file. Required for first initialization.

    Note:
        This function is thread-safe. Multiple threads can safely call this function
        concurrently, and only one will perform the initialization.
    """
    global _metrics_collector
    with _metrics_collector_lock:
        if _metrics_collector is None:
            if db_path is None:
                raise RuntimeError("MetricsCollector not initialized. Provide db_path for first call.")
            _metrics_collector = MetricsCollector(db_path)
    return _metrics_collector
