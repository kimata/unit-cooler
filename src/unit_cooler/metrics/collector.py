#!/usr/bin/env python3
"""
Performance metrics collection and analysis for outdoor unit cooler system.

This module provides functionality to:
- Collect metrics from actuator operations (valve, sensor, etc.)
- Store metrics in SQLite database with contextual information
- Perform statistical analysis and anomaly detection
- Analyze relationships between environmental data and system performance
"""

import datetime
import logging
import pathlib
import sqlite3
import time
import zoneinfo
from contextlib import contextmanager
from typing import Any

# 分析ライブラリ（オプション）
try:
    import numpy as np
    from scipy import stats
    from sklearn.cluster import DBSCAN
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    _ANALYSIS_AVAILABLE = True
except ImportError:
    _ANALYSIS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "Analysis libraries not available. Install numpy, scipy, scikit-learn for advanced analytics."
    )

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")
DEFAULT_DB_PATH = pathlib.Path("data/metrics.db")


class MetricsCollector:
    """Collects and stores performance metrics for outdoor unit cooler system."""

    def __init__(self, db_path: str | pathlib.Path = DEFAULT_DB_PATH):
        """Initialize MetricsCollector with database path."""
        self.db_path = pathlib.Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with required tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create main metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    hour INTEGER NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    valve_operations INTEGER DEFAULT 0,
                    sensor_reads INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    warnings INTEGER DEFAULT 0,
                    valve_on_total_seconds REAL DEFAULT 0,
                    valve_session_count INTEGER DEFAULT 0,
                    valve_duty_cycle_percentage REAL DEFAULT 0,
                    valve_current_state TEXT DEFAULT 'CLOSE',
                    valve_hardware_state TEXT DEFAULT 'CLOSE',
                    valve_duration_sec INTEGER DEFAULT 0,
                    flow_value REAL NULL,
                    sensor_power_state BOOLEAN DEFAULT 1,
                    temperature REAL NULL,
                    humidity REAL NULL,
                    lux REAL NULL,
                    solar_radiation REAL NULL,
                    power_consumption REAL NULL,
                    rain_amount REAL NULL,
                    uptime_seconds REAL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create individual operation metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    system_metrics_id INTEGER NOT NULL,
                    operation_type TEXT NOT NULL,
                    operation_details TEXT,
                    elapsed_time REAL,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (system_metrics_id) REFERENCES system_metrics (id)
                )
            """)

            # Create indexes for better query performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON system_metrics (timestamp)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_metrics_hour ON system_metrics (hour)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_system_metrics_solar_radiation ON system_metrics (solar_radiation)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_operation_metrics_type ON operation_metrics (operation_type)"
            )

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception:
            if conn:
                conn.rollback()
            logging.exception("Database error")
            raise
        finally:
            if conn:
                conn.close()

    def log_system_metrics(
        self,
        counters: dict[str, int],
        valve_timing: dict[str, Any],
        actuator_metrics: dict[str, Any],
        uptime_seconds: float = 0,
        timestamp: datetime.datetime | None = None,
    ) -> int:
        """
        Log system-wide metrics.

        Args:
            counters: Counter metrics (valve_operations, sensor_reads, errors, warnings)
            valve_timing: Valve timing metrics
            actuator_metrics: Actuator state and sensor data
            uptime_seconds: System uptime in seconds
            timestamp: When the metrics were collected (default: now)

        Returns:
            ID of the inserted system_metrics record
        """
        if timestamp is None:
            timestamp = datetime.datetime.now(TIMEZONE)

        hour = timestamp.hour
        day_of_week = timestamp.weekday()

        # Extract actuator data
        valve_info = actuator_metrics.get("valve", {})
        sensor_info = actuator_metrics.get("sensor", {})
        environmental_info = actuator_metrics.get("environmental", {})

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO system_metrics (
                        timestamp, hour, day_of_week,
                        valve_operations, sensor_reads, errors, warnings,
                        valve_on_total_seconds, valve_session_count, valve_duty_cycle_percentage,
                        valve_current_state, valve_hardware_state, valve_duration_sec,
                        flow_value, sensor_power_state,
                        temperature, humidity, lux, solar_radiation, power_consumption, rain_amount,
                        uptime_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        timestamp,
                        hour,
                        day_of_week,
                        counters.get("valve_operations", 0),
                        counters.get("sensor_reads", 0),
                        counters.get("errors", 0),
                        counters.get("warnings", 0),
                        valve_timing.get("total_on_seconds", 0),
                        valve_timing.get("session_count", 0),
                        valve_timing.get("duty_cycle_percentage", 0),
                        valve_timing.get("current_state", "CLOSE"),
                        valve_info.get("state", "CLOSE"),
                        valve_info.get("duration_sec", 0),
                        sensor_info.get("flow_value"),
                        sensor_info.get("power_state", True),
                        environmental_info.get("temperature"),
                        environmental_info.get("humidity"),
                        environmental_info.get("lux"),
                        environmental_info.get("solar_radiation"),
                        environmental_info.get("power_consumption"),
                        environmental_info.get("rain_amount"),
                        uptime_seconds,
                    ),
                )

                conn.commit()
                logging.debug("Logged system metrics at %s", timestamp)
                return cursor.lastrowid

        except Exception:
            logging.exception("Failed to log system metrics")
            return -1

    def log_operation_metrics(
        self,
        system_metrics_id: int,
        operation_type: str,
        operation_details: str | None = None,
        elapsed_time: float | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> int:
        """
        Log individual operation metrics.

        Args:
            system_metrics_id: Reference to system_metrics record
            operation_type: Type of operation (valve_open, valve_close, sensor_read, etc.)
            operation_details: Additional details about the operation
            elapsed_time: Time taken for the operation
            success: Whether the operation succeeded
            error_message: Error message if any

        Returns:
            ID of the inserted record
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO operation_metrics (
                        system_metrics_id, operation_type, operation_details,
                        elapsed_time, success, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        system_metrics_id,
                        operation_type,
                        operation_details,
                        elapsed_time,
                        success,
                        error_message,
                    ),
                )

                conn.commit()
                logging.debug("Logged operation metrics: %s (success=%s)", operation_type, success)
                return cursor.lastrowid

        except Exception:
            logging.exception("Failed to log operation metrics")
            return -1


class MetricsAnalyzer:
    """Analyzes metrics data for patterns and anomalies."""

    def __init__(self, db_path: str | pathlib.Path = DEFAULT_DB_PATH):
        """Initialize MetricsAnalyzer with database path."""
        self.db_path = pathlib.Path(db_path)
        if not self.db_path.exists():
            msg = f"Metrics database not found: {self.db_path}"
            raise FileNotFoundError(msg)

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception:
            logging.exception("Database error")
            raise
        finally:
            if conn:
                conn.close()

    def get_basic_statistics(self, days: int = 30) -> dict:
        """Get basic statistics for the last N days."""
        since = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_records,
                    AVG(valve_duty_cycle_percentage) as avg_duty_cycle,
                    MIN(valve_duty_cycle_percentage) as min_duty_cycle,
                    MAX(valve_duty_cycle_percentage) as max_duty_cycle,
                    SUM(valve_operations) as total_valve_operations,
                    SUM(sensor_reads) as total_sensor_reads,
                    SUM(errors) as total_errors,
                    AVG(temperature) as avg_temperature,
                    AVG(solar_radiation) as avg_solar_radiation,
                    AVG(flow_value) as avg_flow_value
                FROM system_metrics
                WHERE timestamp >= ?
            """,
                (since,),
            )
            stats = dict(cursor.fetchone())

            return {
                "period_days": days,
                "system_metrics": stats,
            }

    def get_hourly_patterns(self, days: int = 30) -> dict:
        """Analyze performance patterns by hour of day."""
        since = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    hour,
                    COUNT(*) as count,
                    AVG(valve_duty_cycle_percentage) as avg_duty_cycle,
                    MIN(valve_duty_cycle_percentage) as min_duty_cycle,
                    MAX(valve_duty_cycle_percentage) as max_duty_cycle,
                    AVG(temperature) as avg_temperature,
                    AVG(solar_radiation) as avg_solar_radiation,
                    SUM(errors) * 100.0 / NULLIF(SUM(valve_operations + sensor_reads), 0) as error_rate
                FROM system_metrics
                WHERE timestamp >= ?
                GROUP BY hour
                ORDER BY hour
            """,
                (since,),
            )
            hourly_data = [dict(row) for row in cursor.fetchall()]

            # Get raw data for boxplots
            cursor.execute(
                """
                SELECT hour, valve_duty_cycle_percentage, temperature, solar_radiation
                FROM system_metrics
                WHERE timestamp >= ?
                ORDER BY hour
            """,
                (since,),
            )
            raw_data = cursor.fetchall()

            # Group raw data by hour for boxplots
            hourly_boxplot = {}
            for row in raw_data:
                hour = row[0]
                if hour not in hourly_boxplot:
                    hourly_boxplot[hour] = {
                        "duty_cycle": [],
                        "temperature": [],
                        "solar_radiation": [],
                    }
                hourly_boxplot[hour]["duty_cycle"].append(row[1])
                if row[2] is not None:
                    hourly_boxplot[hour]["temperature"].append(row[2])
                if row[3] is not None:
                    hourly_boxplot[hour]["solar_radiation"].append(row[3])

            return {
                "hourly_stats": hourly_data,
                "hourly_boxplot": hourly_boxplot,
            }

    def detect_anomalies(self, days: int = 30, contamination: float = 0.1) -> dict:
        """
        Detect anomalies in system metrics using Isolation Forest.

        Args:
            days: Number of days to analyze
            contamination: Expected proportion of anomalies (0.0 to 0.5)

        Returns:
            Dictionary with anomaly detection results
        """
        if not _ANALYSIS_AVAILABLE:
            return {"error": "Analysis libraries not available"}

        since = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, timestamp, hour, day_of_week, valve_duty_cycle_percentage,
                       temperature, solar_radiation, flow_value, errors
                FROM system_metrics
                WHERE timestamp >= ?
                ORDER BY timestamp
            """,
                (since,),
            )
            data = [dict(row) for row in cursor.fetchall()]

        if len(data) < 10:
            return {"error": "Insufficient data for anomaly detection (need at least 10 records)"}

        try:
            # Prepare features for anomaly detection
            features = []
            for row in data:
                feature_row = [
                    row["hour"],
                    row["day_of_week"],
                    row["valve_duty_cycle_percentage"],
                    row.get("temperature") or 25.0,  # Default temperature
                    row.get("solar_radiation") or 0.0,  # Default solar radiation
                    row.get("flow_value") or 0.0,  # Default flow value
                    row["errors"],
                ]
                features.append(feature_row)

            features_array = np.array(features)
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features_array)

            isolation_forest = IsolationForest(contamination=contamination, random_state=42)
            anomaly_labels = isolation_forest.fit_predict(features_scaled)

            anomalies = []
            for i, label in enumerate(anomaly_labels):
                if label == -1:  # Anomaly
                    anomalies.append(
                        {
                            "id": data[i]["id"],
                            "timestamp": data[i]["timestamp"],
                            "duty_cycle": data[i]["valve_duty_cycle_percentage"],
                            "hour": data[i]["hour"],
                            "temperature": data[i].get("temperature"),
                            "solar_radiation": data[i].get("solar_radiation"),
                            "flow_value": data[i].get("flow_value"),
                            "errors": data[i]["errors"],
                        }
                    )

            return {
                "total_samples": len(data),
                "anomalies_detected": len(anomalies),
                "anomaly_rate": len(anomalies) / len(data),
                "anomalies": anomalies,
            }

        except Exception as e:
            logging.exception("Error in anomaly detection")
            return {"error": f"Anomaly detection failed: {e}"}

    def get_correlation_analysis(self, days: int = 30) -> dict:
        """Analyze correlations between environmental factors and system performance."""
        if not _ANALYSIS_AVAILABLE:
            return {"error": "Analysis libraries not available"}

        since = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=days)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT valve_duty_cycle_percentage, temperature, humidity, solar_radiation,
                       power_consumption, rain_amount, flow_value
                FROM system_metrics
                WHERE timestamp >= ?
                  AND temperature IS NOT NULL
                  AND solar_radiation IS NOT NULL
            """,
                (since,),
            )
            data = [dict(row) for row in cursor.fetchall()]

        if len(data) < 10:
            return {"error": "Insufficient data for correlation analysis (need at least 10 records)"}

        try:
            correlations = {}
            duty_cycles = [row["valve_duty_cycle_percentage"] for row in data]

            # Environmental factors to analyze
            factors = [
                ("temperature", "Temperature", "°C"),
                ("humidity", "Humidity", "%"),
                ("solar_radiation", "Solar Radiation", "W/m²"),
                ("power_consumption", "Power Consumption", "W"),
                ("rain_amount", "Rain Amount", "mm/h"),
                ("flow_value", "Flow Value", "L/min"),
            ]

            for factor, name, unit in factors:
                factor_values = [row[factor] for row in data if row.get(factor) is not None]
                if len(factor_values) >= 10:
                    # Get corresponding duty cycle values
                    paired_data = [
                        (row[factor], row["valve_duty_cycle_percentage"])
                        for row in data
                        if row.get(factor) is not None
                    ]
                    factor_vals, duty_vals = zip(*paired_data)

                    correlation_coef, p_value = stats.pearsonr(factor_vals, duty_vals)

                    correlations[factor] = {
                        "name": name,
                        "unit": unit,
                        "correlation_coefficient": float(correlation_coef),
                        "p_value": float(p_value),
                        "significance": "significant" if p_value < 0.05 else "not_significant",
                        "strength": (
                            "strong"
                            if abs(correlation_coef) > 0.7
                            else "moderate"
                            if abs(correlation_coef) > 0.3
                            else "weak"
                        ),
                        "direction": "positive" if correlation_coef > 0 else "negative",
                        "data_points": len(paired_data),
                    }

            # Create ranking
            significant_correlations = [
                (factor, info)
                for factor, info in correlations.items()
                if info["significance"] == "significant"
            ]
            significant_correlations.sort(key=lambda x: abs(x[1]["correlation_coefficient"]), reverse=True)

            return {
                "correlations": correlations,
                "ranking": {
                    "most_influential_factors": [
                        {
                            "factor": factor,
                            "name": info["name"],
                            "correlation_coefficient": info["correlation_coefficient"],
                            "strength": info["strength"],
                            "direction": info["direction"],
                            "unit": info["unit"],
                        }
                        for factor, info in significant_correlations[:5]
                    ],
                    "total_significant": len(significant_correlations),
                    "total_analyzed": len(correlations),
                },
            }

        except Exception as e:
            logging.exception("Error in correlation analysis")
            return {"error": f"Correlation analysis failed: {e}"}

    def check_performance_alerts(self, thresholds: dict | None = None) -> list[dict]:
        """
        Check for performance alerts based on thresholds.

        Args:
            thresholds: Custom thresholds (default: reasonable values)

        Returns:
            List of alert dictionaries
        """
        if thresholds is None:
            thresholds = {
                "max_duty_cycle": 90.0,  # percent
                "max_temperature": 40.0,  # celsius
                "error_rate_threshold": 5.0,  # percent
                "recent_hours": 24,  # hours to check
            }

        alerts = []
        since = datetime.datetime.now(TIMEZONE) - datetime.timedelta(hours=thresholds["recent_hours"])

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check for high duty cycle
            cursor.execute(
                """
                SELECT COUNT(*) as high_duty_count, MAX(valve_duty_cycle_percentage) as max_duty
                FROM system_metrics
                WHERE timestamp >= ? AND valve_duty_cycle_percentage > ?
            """,
                (since, thresholds["max_duty_cycle"]),
            )
            row = cursor.fetchone()
            if row["high_duty_count"] > 0:
                alerts.append(
                    {
                        "type": "high_duty_cycle",
                        "message": (
                            f"Found {row['high_duty_count']} high duty cycle occurrences "
                            f"(max: {row['max_duty']:.1f}%)"
                        ),
                        "severity": "warning",
                    }
                )

            # Check for high temperature
            cursor.execute(
                """
                SELECT COUNT(*) as high_temp_count, MAX(temperature) as max_temp
                FROM system_metrics
                WHERE timestamp >= ? AND temperature > ?
            """,
                (since, thresholds["max_temperature"]),
            )
            row = cursor.fetchone()
            if row["high_temp_count"] > 0:
                alerts.append(
                    {
                        "type": "high_temperature",
                        "message": (
                            f"Found {row['high_temp_count']} high temperature occurrences "
                            f"(max: {row['max_temp']:.1f}°C)"
                        ),
                        "severity": "critical",
                    }
                )

            # Check error rates
            cursor.execute(
                """
                SELECT
                    SUM(errors) * 100.0 / NULLIF(SUM(valve_operations + sensor_reads), 0) as error_rate
                FROM system_metrics
                WHERE timestamp >= ?
            """,
                (since,),
            )
            row = cursor.fetchone()
            if row["error_rate"] and row["error_rate"] > thresholds["error_rate_threshold"]:
                alerts.append(
                    {
                        "type": "high_error_rate",
                        "message": f"High error rate: {row['error_rate']:.1f}%",
                        "severity": "critical",
                    }
                )

        return alerts


# Global instance for easy access
_metrics_collector = None


def get_metrics_collector(db_path: str | pathlib.Path = DEFAULT_DB_PATH) -> MetricsCollector:
    """Get or create global metrics collector instance."""
    global _metrics_collector  # noqa: PLW0603
    if _metrics_collector is None or _metrics_collector.db_path != pathlib.Path(db_path):
        _metrics_collector = MetricsCollector(db_path)
    return _metrics_collector


def collect_system_metrics(*args, db_path: str | pathlib.Path | None = None, **kwargs) -> int:
    """Collect system metrics with convenience wrapper."""
    if db_path is not None:
        kwargs.pop("db_path", None)  # Remove db_path from kwargs to avoid duplicate
        return get_metrics_collector(db_path).log_system_metrics(*args, **kwargs)
    return get_metrics_collector().log_system_metrics(*args, **kwargs)


def collect_operation_metrics(*args, db_path: str | pathlib.Path | None = None, **kwargs) -> int:
    """Collect operation metrics with convenience wrapper."""
    if db_path is not None:
        kwargs.pop("db_path", None)  # Remove db_path from kwargs to avoid duplicate
        return get_metrics_collector(db_path).log_operation_metrics(*args, **kwargs)
    return get_metrics_collector().log_operation_metrics(*args, **kwargs)
