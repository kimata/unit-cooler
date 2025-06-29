"""アクチュエータのメトリクス情報を公開するAPI"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import flask
import my_lib.flask_util
import my_lib.footprint
import my_lib.webapp.config

import unit_cooler.actuator.sensor
import unit_cooler.actuator.valve
import unit_cooler.const

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

# グローバルメトリクス管理
_metrics_lock = threading.Lock()
_metrics_data = {
    "valve_operations": 0,
    "sensor_reads": 0,
    "errors": 0,
    "warnings": 0,
    "last_valve_operation": None,
    "last_sensor_read": None,
    "last_error": None,
    "uptime_start": time.time(),
    # バルブ稼働時間関連
    "valve_on_total_seconds": 0.0,
    "valve_on_session_count": 0,
    "valve_last_on_time": None,
    "valve_current_state": "CLOSE",
    "valve_session_times": [],  # 最新10セッションの記録
}

blueprint = flask.Blueprint("metrics", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)

logger = logging.getLogger(__name__)

# データベース設定
_db_path = None
_db_lock = threading.Lock()


def init_metrics_db():
    """メトリクスデータベースの初期化"""
    global _db_path  # noqa: PLW0603

    try:
        # Flaskアプリのconfigからパスを取得
        config = flask.current_app.config.get("CONFIG", {})
        _db_path = (
            config.get("actuator", {})
            .get("log_server", {})
            .get("webapp", {})
            .get("data", {})
            .get("metrics_db_path")
        )

        if not _db_path:
            logger.warning("metrics_db_path not configured, using default")
            _db_path = "data/metrics.db"

        # データベースファイルのディレクトリを作成
        db_path = Path(_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # テーブル作成
        with _db_lock:
            conn = sqlite3.connect(_db_path)
            cursor = conn.cursor()

            # メトリクステーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
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
                    -- センサーデータ
                    temperature REAL NULL,
                    humidity REAL NULL,
                    lux REAL NULL,
                    solar_radiation REAL NULL,
                    power_consumption REAL NULL,
                    rain_amount REAL NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 既存テーブルにセンサーデータカラムを追加（存在しない場合のみ）
            sensor_columns = [
                ("temperature", "REAL NULL"),
                ("humidity", "REAL NULL"),
                ("lux", "REAL NULL"),
                ("solar_radiation", "REAL NULL"),
                ("power_consumption", "REAL NULL"),
                ("rain_amount", "REAL NULL"),
            ]

            import contextlib

            for column_name, column_type in sensor_columns:
                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute(f"ALTER TABLE metrics ADD COLUMN {column_name} {column_type}")

            # インデックス作成
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_created_at ON metrics(created_at)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_solar_radiation ON metrics(solar_radiation)"
            )

            conn.commit()
            conn.close()

        logger.info("Metrics database initialized: %s", _db_path)

    except Exception:
        logger.exception("Error initializing metrics database")
        _db_path = None


def save_metrics_to_db(metrics_data: dict[str, Any]):
    """メトリクスをデータベースに保存"""
    global _db_path

    if not _db_path:
        return

    try:
        with _db_lock:
            conn = sqlite3.connect(_db_path)
            cursor = conn.cursor()

            # メトリクスデータを抽出
            counters = metrics_data.get("counters", {})
            valve_timing = metrics_data.get("valve_timing", {})
            actuator = metrics_data.get("actuator", {})

            valve_info = actuator.get("valve", {})
            sensor_info = actuator.get("sensor", {})
            environmental_info = actuator.get("environmental", {})

            # データベースに挿入
            cursor.execute(
                """
                INSERT INTO metrics (
                    timestamp,
                    valve_operations,
                    sensor_reads,
                    errors,
                    warnings,
                    valve_on_total_seconds,
                    valve_session_count,
                    valve_duty_cycle_percentage,
                    valve_current_state,
                    valve_hardware_state,
                    valve_duration_sec,
                    flow_value,
                    sensor_power_state,
                    temperature,
                    humidity,
                    lux,
                    solar_radiation,
                    power_consumption,
                    rain_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metrics_data.get("timestamp", time.time()),
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
                ),
            )

            conn.commit()
            conn.close()

            logger.debug("Metrics saved to database")

    except Exception:
        logger.exception("Error saving metrics to database")


def get_metrics_from_db(hours: int = 24) -> list:
    """データベースからメトリクスを取得"""
    global _db_path

    if not _db_path:
        return []

    try:
        with _db_lock:
            conn = sqlite3.connect(_db_path)
            cursor = conn.cursor()

            # 過去N時間のデータを取得
            since_timestamp = time.time() - (hours * 3600)

            cursor.execute(
                """
                SELECT
                    timestamp,
                    valve_operations,
                    sensor_reads,
                    errors,
                    warnings,
                    valve_on_total_seconds,
                    valve_session_count,
                    valve_duty_cycle_percentage,
                    valve_current_state,
                    valve_hardware_state,
                    valve_duration_sec,
                    flow_value,
                    sensor_power_state,
                    temperature,
                    humidity,
                    lux,
                    solar_radiation,
                    power_consumption,
                    rain_amount,
                    created_at
                FROM metrics
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 1000
            """,
                (since_timestamp,),
            )

            rows = cursor.fetchall()
            conn.close()

            # 辞書形式に変換
            columns = [
                "timestamp",
                "valve_operations",
                "sensor_reads",
                "errors",
                "warnings",
                "valve_on_total_seconds",
                "valve_session_count",
                "valve_duty_cycle_percentage",
                "valve_current_state",
                "valve_hardware_state",
                "valve_duration_sec",
                "flow_value",
                "sensor_power_state",
                "temperature",
                "humidity",
                "lux",
                "solar_radiation",
                "power_consumption",
                "rain_amount",
                "created_at",
            ]

            return [dict(zip(columns, row, strict=True)) for row in rows]

    except Exception:
        logger.exception("Error reading metrics from database")
        return []


@blueprint.route("/api/metrics/history", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_metrics_history():
    """過去のメトリクス履歴を取得"""
    try:
        # クエリパラメータから時間範囲を取得
        hours = int(flask.request.args.get("hours", 24))
        limit = int(flask.request.args.get("limit", 1000))

        # データベースから取得
        history_data = get_metrics_from_db(hours)

        # 必要に応じて制限
        if len(history_data) > limit:
            history_data = history_data[:limit]

        response = {
            "timestamp": time.time(),
            "hours": hours,
            "count": len(history_data),
            "data": history_data,
        }

        return flask.jsonify(response)

    except Exception as e:
        logger.exception("Error getting metrics history")
        return flask.jsonify({"error": str(e), "timestamp": time.time()}), 500


def increment_metric(metric_name: str, details: dict[str, Any] | None = None):
    """メトリクスカウンタを増加させる"""
    with _metrics_lock:
        if metric_name in _metrics_data:
            _metrics_data[metric_name] += 1

        # 詳細情報を記録
        timestamp = time.time()
        if metric_name == "valve_operations":
            _metrics_data["last_valve_operation"] = {"timestamp": timestamp, "details": details or {}}
        elif metric_name == "sensor_reads":
            _metrics_data["last_sensor_read"] = {"timestamp": timestamp, "details": details or {}}
        elif metric_name == "errors":
            _metrics_data["last_error"] = {"timestamp": timestamp, "details": details or {}}


def _get_sensor_data() -> dict[str, Any]:
    """センサーデータ取得のヘルパー関数"""
    sense_data = {}
    try:
        import unit_cooler.actuator.control

        current_message = unit_cooler.actuator.control.get_control_message()
        if current_message and "sense_data" in current_message:
            sense_data = current_message["sense_data"]
    except Exception:
        # センサーデータが取得できない場合は空の辞書
        sense_data = {}

    # センサーデータの解析
    sensor_values = {
        "temperature": None,
        "humidity": None,
        "lux": None,
        "solar_radiation": None,
        "power_consumption": None,
        "rain_amount": None,
    }

    if sense_data:
        # 各センサーデータから最新値を取得
        if temp_data := sense_data.get("temp"):
            sensor_values["temperature"] = temp_data[0].get("value")
        if humi_data := sense_data.get("humi"):
            sensor_values["humidity"] = humi_data[0].get("value")
        if lux_data := sense_data.get("lux"):
            sensor_values["lux"] = lux_data[0].get("value")
        if solar_data := sense_data.get("solar_rad"):
            sensor_values["solar_radiation"] = solar_data[0].get("value")
        if power_data := sense_data.get("power"):
            # 電力は複数のセンサーがある場合は合計する
            total_power = sum(item.get("value", 0) for item in power_data if item.get("value") is not None)
            sensor_values["power_consumption"] = total_power if total_power > 0 else None
        if rain_data := sense_data.get("rain"):
            sensor_values["rain_amount"] = rain_data[0].get("value")

    return sensor_values


def get_actuator_specific_metrics() -> dict[str, Any]:
    """アクチュエータ固有のメトリクスを収集（システム情報は別API利用）"""
    try:
        # バルブ状態の取得
        valve_status = unit_cooler.actuator.valve.get_status()
        valve_state = valve_status["state"].name
        valve_duration = valve_status["duration"]

        # フロー情報の取得
        flow = unit_cooler.actuator.sensor.get_flow(force_power_on=False)
        sensor_power_state = unit_cooler.actuator.sensor.get_power_state()

        # ファイルベースのステータス情報
        stat_dir = Path("/dev/shm/unit_cooler")  # noqa: S108
        valve_working = my_lib.footprint.exists(unit_cooler.actuator.valve.STAT_PATH_VALVE_STATE_WORKING)
        valve_idle = my_lib.footprint.exists(unit_cooler.actuator.valve.STAT_PATH_VALVE_STATE_IDLE)

        # 作業履歴の情報（テスト環境での履歴）
        valve_hist_count = 0
        try:
            valve_hist = unit_cooler.actuator.valve.get_hist()
            valve_hist_count = len(valve_hist)
        except Exception:
            # 履歴の取得に失敗した場合はデフォルト値を使用
            valve_hist_count = 0

        # センサーデータの取得
        sensor_values = _get_sensor_data()

        return {
            "valve": {
                "state": valve_state,
                "duration_sec": valve_duration,
                "is_working": valve_working,
                "is_idle": valve_idle,
                "history_count": valve_hist_count,
            },
            "sensor": {
                "flow_value": flow,
                "power_state": sensor_power_state,
                "flow_available": flow is not None,
            },
            "environmental": sensor_values,
            "actuator": {"timestamp": time.time(), "stat_dir_exists": stat_dir.exists()},
        }
    except Exception as e:
        logger.exception("Error collecting actuator metrics")
        return {"error": str(e)}


@blueprint.route("/api/metrics", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_metrics_json():
    """メトリクス情報をJSON形式で返す"""
    try:
        with _metrics_lock:
            current_metrics = _metrics_data.copy()

        # アクチュエータ固有メトリクスを追加
        actuator_metrics = get_actuator_specific_metrics()

        # 稼働時間の計算
        uptime_seconds = time.time() - current_metrics["uptime_start"]

        # バルブ稼働時間メトリクスを取得
        valve_timing = get_valve_timing_metrics()

        response = {
            "timestamp": time.time(),
            "uptime_seconds": uptime_seconds,
            "counters": {
                "valve_operations": current_metrics["valve_operations"],
                "sensor_reads": current_metrics["sensor_reads"],
                "errors": current_metrics["errors"],
                "warnings": current_metrics["warnings"],
            },
            "valve_timing": valve_timing,
            "last_events": {
                "valve_operation": current_metrics["last_valve_operation"],
                "sensor_read": current_metrics["last_sensor_read"],
                "error": current_metrics["last_error"],
            },
            "actuator": actuator_metrics,
            "note": "For system metrics (CPU, memory, etc.), use /unit_cooler/api/sysinfo",
        }

        # データベースに保存
        save_metrics_to_db(response)

        return flask.jsonify(response)

    except Exception as e:
        logger.exception("Error generating metrics")
        return flask.jsonify({"error": str(e), "timestamp": time.time()}), 500


@blueprint.route("/api/metrics/prometheus", methods=["GET"])
def get_metrics_prometheus():
    """メトリクス情報をPrometheus形式で返す"""
    try:
        with _metrics_lock:
            current_metrics = _metrics_data.copy()

        actuator_metrics = get_actuator_specific_metrics()
        valve_timing = get_valve_timing_metrics()
        uptime_seconds = time.time() - current_metrics["uptime_start"]

        # Prometheus形式のメトリクス生成
        prom_lines = []

        # ヘルプとタイプ情報
        prom_lines.extend(
            [
                "# HELP unit_cooler_actuator_valve_operations_total Total number of valve operations",
                "# TYPE unit_cooler_actuator_valve_operations_total counter",
                f"unit_cooler_actuator_valve_operations_total {current_metrics['valve_operations']}",
                "",
                "# HELP unit_cooler_actuator_sensor_reads_total Total number of sensor reads",
                "# TYPE unit_cooler_actuator_sensor_reads_total counter",
                f"unit_cooler_actuator_sensor_reads_total {current_metrics['sensor_reads']}",
                "",
                "# HELP unit_cooler_actuator_errors_total Total number of errors",
                "# TYPE unit_cooler_actuator_errors_total counter",
                f"unit_cooler_actuator_errors_total {current_metrics['errors']}",
                "",
                "# HELP unit_cooler_actuator_uptime_seconds Actuator uptime in seconds",
                "# TYPE unit_cooler_actuator_uptime_seconds gauge",
                f"unit_cooler_actuator_uptime_seconds {uptime_seconds:.2f}",
                "",
                "# HELP unit_cooler_actuator_valve_on_total_seconds Total valve ON time in seconds",
                "# TYPE unit_cooler_actuator_valve_on_total_seconds counter",
                f"unit_cooler_actuator_valve_on_total_seconds {valve_timing['total_on_seconds']:.2f}",
                "",
                "# HELP unit_cooler_actuator_valve_sessions_total Total number of valve ON sessions",
                "# TYPE unit_cooler_actuator_valve_sessions_total counter",
                f"unit_cooler_actuator_valve_sessions_total {valve_timing['session_count']}",
                "",
                "# HELP unit_cooler_actuator_valve_duty_cycle_percentage Valve duty cycle percentage",
                "# TYPE unit_cooler_actuator_valve_duty_cycle_percentage gauge",
                (
                    f"unit_cooler_actuator_valve_duty_cycle_percentage "
                    f"{valve_timing['duty_cycle_percentage']:.2f}"
                ),
                "",
                "# HELP unit_cooler_actuator_valve_average_session_duration_seconds",
                "# Average valve ON session duration",
                "# TYPE unit_cooler_actuator_valve_average_session_duration_seconds gauge",
                (
                    f"unit_cooler_actuator_valve_average_session_duration_seconds "
                    f"{valve_timing['average_session_duration_seconds']:.2f}"
                ),
                "",
            ]
        )

        # アクチュエータメトリクス
        if "valve" in actuator_metrics:
            valve_state_value = 1 if actuator_metrics["valve"]["state"] == "OPEN" else 0
            prom_lines.extend(
                [
                    "# HELP unit_cooler_actuator_valve_state Current valve state (1=OPEN, 0=CLOSE)",
                    "# TYPE unit_cooler_actuator_valve_state gauge",
                    f"unit_cooler_actuator_valve_state {valve_state_value}",
                    "",
                    "# HELP unit_cooler_actuator_valve_duration_seconds Valve current state duration",
                    "# TYPE unit_cooler_actuator_valve_duration_seconds gauge",
                    (
                        f"unit_cooler_actuator_valve_duration_seconds "
                        f"{actuator_metrics['valve']['duration_sec']}"
                    ),
                    "",
                ]
            )

        if "sensor" in actuator_metrics and actuator_metrics["sensor"]["flow_value"] is not None:
            prom_lines.extend(
                [
                    "# HELP unit_cooler_actuator_flow_value Current flow value",
                    "# TYPE unit_cooler_actuator_flow_value gauge",
                    f"unit_cooler_actuator_flow_value {actuator_metrics['sensor']['flow_value']:.2f}",
                    "",
                ]
            )

        response_text = "\n".join(prom_lines)

        return flask.Response(response_text, mimetype="text/plain; version=0.0.4; charset=utf-8")

    except Exception as e:
        logger.exception("Error generating Prometheus metrics")
        return flask.Response(f"# Error generating metrics: {e}\n", status=500, mimetype="text/plain")


@blueprint.route("/api/metrics/health", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_health():
    """ヘルスチェック用エンドポイント"""
    try:
        actuator_metrics = get_actuator_specific_metrics()

        # 基本的な健全性チェック
        is_healthy = True
        issues = []

        if "error" in actuator_metrics:
            is_healthy = False
            issues.append(f"Actuator metrics error: {actuator_metrics['error']}")

        if "sensor" in actuator_metrics and not actuator_metrics["sensor"]["power_state"]:
            issues.append("Sensor power is off")

        response = {"healthy": is_healthy, "timestamp": time.time(), "issues": issues, "version": "1.0.0"}

        status_code = 200 if is_healthy else 503
        return flask.jsonify(response), status_code

    except Exception as e:
        logger.exception("Health check error")
        return flask.jsonify({"healthy": False, "error": str(e), "timestamp": time.time()}), 500


# メトリクス収集のためのヘルパー関数（他のモジュールから呼び出し可能）
def record_valve_operation(operation: str, state: str):
    """バルブ操作を記録"""
    increment_metric("valve_operations", {"operation": operation, "state": state, "source": "valve_module"})

    # バルブ稼働時間の記録
    _record_valve_timing(state)


def record_sensor_read(sensor_type: str, value: Any):
    """センサー読み取りを記録"""
    increment_metric("sensor_reads", {"sensor_type": sensor_type, "value": value, "source": "sensor_module"})


def record_error(error_type: str, message: str):
    """エラーを記録"""
    increment_metric("errors", {"error_type": error_type, "message": message, "source": "general"})


def record_warning(warning_type: str, message: str):
    """警告を記録"""
    increment_metric("warnings", {"warning_type": warning_type, "message": message, "source": "general"})


def _record_valve_timing(new_state: str):
    """バルブ稼働時間の内部記録"""
    with _metrics_lock:
        current_time = time.time()
        prev_state = _metrics_data["valve_current_state"]

        # CLOSE → OPEN への変化
        if prev_state == "CLOSE" and new_state == "OPEN":
            _metrics_data["valve_last_on_time"] = current_time
            _metrics_data["valve_current_state"] = "OPEN"

        # OPEN → CLOSE への変化
        elif prev_state == "OPEN" and new_state == "CLOSE":
            if _metrics_data["valve_last_on_time"] is not None:
                # ON時間を計算
                session_duration = current_time - _metrics_data["valve_last_on_time"]
                _metrics_data["valve_on_total_seconds"] += session_duration
                _metrics_data["valve_on_session_count"] += 1

                # セッション履歴を記録（最新10件）
                session_info = {
                    "start_time": _metrics_data["valve_last_on_time"],
                    "end_time": current_time,
                    "duration_seconds": session_duration,
                }
                _metrics_data["valve_session_times"].append(session_info)
                if len(_metrics_data["valve_session_times"]) > 10:
                    _metrics_data["valve_session_times"].pop(0)

                _metrics_data["valve_last_on_time"] = None
            _metrics_data["valve_current_state"] = "CLOSE"


def get_valve_timing_metrics() -> dict[str, Any]:
    """バルブ稼働時間メトリクスを取得"""
    with _metrics_lock:
        current_time = time.time()
        uptime_seconds = current_time - _metrics_data["uptime_start"]

        # 現在ONの場合、その時間も加算して計算
        current_session_duration = 0
        if _metrics_data["valve_current_state"] == "OPEN" and _metrics_data["valve_last_on_time"] is not None:
            current_session_duration = current_time - _metrics_data["valve_last_on_time"]

        total_on_time = _metrics_data["valve_on_total_seconds"] + current_session_duration

        # 各種計算値
        duty_cycle_ratio = (total_on_time / uptime_seconds * 100) if uptime_seconds > 0 else 0
        average_session_duration = 0
        if _metrics_data["valve_on_session_count"] > 0:
            # 現在のセッションも平均に含める
            session_count = _metrics_data["valve_on_session_count"]
            if current_session_duration > 0:
                session_count += 1
            average_session_duration = total_on_time / session_count

        return {
            "total_on_seconds": total_on_time,
            "session_count": _metrics_data["valve_on_session_count"],
            "average_session_duration_seconds": average_session_duration,
            "duty_cycle_percentage": duty_cycle_ratio,
            "current_state": _metrics_data["valve_current_state"],
            "current_session_duration": current_session_duration,
            "recent_sessions": _metrics_data["valve_session_times"][-5:],  # 最新5件
            "uptime_seconds": uptime_seconds,
        }


# メトリクス分析機能ヘルパー関数
def _calculate_basic_statistics(data: list[dict[str, Any]]) -> dict[str, Any]:
    """基本統計の計算"""
    timestamps = [row["timestamp"] for row in data]
    valve_operations = [row["valve_operations"] for row in data]
    sensor_reads = [row["sensor_reads"] for row in data]
    errors = [row["errors"] for row in data]
    duty_cycles = [row["valve_duty_cycle_percentage"] for row in data]

    return {
        "timestamp_range": {
            "start": min(timestamps),
            "end": max(timestamps),
            "duration_hours": (max(timestamps) - min(timestamps)) / 3600,
        },
        "valve_operations": {
            "total": max(valve_operations) if valve_operations else 0,
            "rate_per_hour": (max(valve_operations) if valve_operations else 0)
            / ((max(timestamps) - min(timestamps)) / 3600)
            if len(timestamps) > 1
            else 0,
        },
        "sensor_reads": {
            "total": max(sensor_reads) if sensor_reads else 0,
            "rate_per_hour": (max(sensor_reads) if sensor_reads else 0)
            / ((max(timestamps) - min(timestamps)) / 3600)
            if len(timestamps) > 1
            else 0,
        },
        "error_analysis": {
            "total_errors": max(errors) if errors else 0,
            "error_rate": (max(errors) if errors else 0) / (max(sensor_reads) if sensor_reads else 1),
        },
        "duty_cycle_analysis": {
            "mean": float(np.mean(duty_cycles)) if duty_cycles else 0,
            "std": float(np.std(duty_cycles)) if duty_cycles else 0,
            "min": float(np.min(duty_cycles)) if duty_cycles else 0,
            "max": float(np.max(duty_cycles)) if duty_cycles else 0,
            "median": float(np.median(duty_cycles)) if duty_cycles else 0,
        },
    }


def _calculate_flow_analysis(flow_values: list) -> dict[str, Any]:
    """フロー値統計の計算"""
    if not flow_values:
        return {}

    return {
        "flow_analysis": {
            "mean": float(np.mean(flow_values)),
            "std": float(np.std(flow_values)),
            "min": float(np.min(flow_values)),
            "max": float(np.max(flow_values)),
            "median": float(np.median(flow_values)),
            "percentile_95": float(np.percentile(flow_values, 95)),
            "normal_test": {
                "statistic": float(stats.normaltest(flow_values)[0]),
                "p_value": float(stats.normaltest(flow_values)[1]),
                "is_normal": float(stats.normaltest(flow_values)[1]) > 0.05,
            },
        }
    }


def _calculate_environmental_analysis(
    solar_radiation_values: list, temperatures: list, humidity_values: list
) -> dict[str, Any]:
    """環境データ統計の計算"""
    if not solar_radiation_values:
        return {}

    env_analysis = {
        "environmental_analysis": {
            "solar_radiation": {
                "mean": float(np.mean(solar_radiation_values)),
                "std": float(np.std(solar_radiation_values)),
                "min": float(np.min(solar_radiation_values)),
                "max": float(np.max(solar_radiation_values)),
                "median": float(np.median(solar_radiation_values)),
            },
        }
    }

    if temperatures:
        env_analysis["environmental_analysis"]["temperature"] = {
            "mean": float(np.mean(temperatures)),
            "std": float(np.std(temperatures)),
            "min": float(np.min(temperatures)),
            "max": float(np.max(temperatures)),
        }

    if humidity_values:
        env_analysis["environmental_analysis"]["humidity"] = {
            "mean": float(np.mean(humidity_values)),
            "std": float(np.std(humidity_values)),
        }

    return env_analysis


def _calculate_correlation_analysis(data: list[dict[str, Any]], duty_cycles: list) -> dict[str, Any]:
    """相関分析の計算"""
    if len(duty_cycles) <= 10:
        return {}

    # センサーデータを取得
    temperatures = [row["temperature"] for row in data if row.get("temperature") is not None]
    humidity_values = [row["humidity"] for row in data if row.get("humidity") is not None]
    lux_values = [row["lux"] for row in data if row.get("lux") is not None]
    solar_radiation_values = [
        row["solar_radiation"] for row in data if row.get("solar_radiation") is not None
    ]
    power_values = [row["power_consumption"] for row in data if row.get("power_consumption") is not None]
    rain_values = [row["rain_amount"] for row in data if row.get("rain_amount") is not None]
    flow_values = [row["flow_value"] for row in data if row["flow_value"] is not None]

    correlation_analysis = {"correlation_analysis": {}}
    correlation_results = []

    # センサーデータのリスト（名前、データ、単位）
    sensor_datasets = [
        ("solar_radiation", solar_radiation_values, "W/m²"),
        ("temperature", temperatures, "°C"),
        ("humidity", humidity_values, "%"),
        ("lux", lux_values, "lux"),
        ("power_consumption", power_values, "W"),
        ("rain_amount", rain_values, "mm/h"),
    ]

    for sensor_name, sensor_values, unit in sensor_datasets:
        if len(sensor_values) > 10:
            # リスト内包表記を使用
            sensor_duty_pairs = [
                (row[sensor_name], row["valve_duty_cycle_percentage"])
                for row in data
                if row.get(sensor_name) is not None and row["valve_duty_cycle_percentage"] is not None
            ]

            if len(sensor_duty_pairs) > 10:
                sensor_vals, duty_vals = zip(*sensor_duty_pairs, strict=True)
                correlation_coef, correlation_p_value = stats.pearsonr(sensor_vals, duty_vals)

                correlation_info = {
                    "correlation_coefficient": float(correlation_coef),
                    "p_value": float(correlation_p_value),
                    "significance": "significant" if correlation_p_value < 0.05 else "not_significant",
                    "strength": (
                        "strong"
                        if abs(correlation_coef) > 0.7
                        else "moderate"
                        if abs(correlation_coef) > 0.3
                        else "weak"
                    ),
                    "direction": "positive" if correlation_coef > 0 else "negative",
                    "data_points": len(sensor_duty_pairs),
                    "unit": unit,
                    "abs_correlation": abs(correlation_coef),
                }

                correlation_analysis["correlation_analysis"][f"{sensor_name}_vs_duty_cycle"] = (
                    correlation_info
                )
                correlation_results.append((sensor_name, correlation_info))

    # フロー値との相関
    if flow_values and len(flow_values) > 10:
        flow_duty_pairs = [
            (row["flow_value"], row["valve_duty_cycle_percentage"])
            for row in data
            if row.get("flow_value") is not None and row["valve_duty_cycle_percentage"] is not None
        ]

        if len(flow_duty_pairs) > 10:
            flow_vals, duty_vals_flow = zip(*flow_duty_pairs, strict=True)
            flow_correlation_coef, flow_correlation_p_value = stats.pearsonr(flow_vals, duty_vals_flow)

            correlation_analysis["correlation_analysis"]["flow_value_vs_duty_cycle"] = {
                "correlation_coefficient": float(flow_correlation_coef),
                "p_value": float(flow_correlation_p_value),
                "significance": "significant" if flow_correlation_p_value < 0.05 else "not_significant",
                "strength": (
                    "strong"
                    if abs(flow_correlation_coef) > 0.7
                    else "moderate"
                    if abs(flow_correlation_coef) > 0.3
                    else "weak"
                ),
                "direction": "positive" if flow_correlation_coef > 0 else "negative",
                "data_points": len(flow_duty_pairs),
                "unit": "L/min",
            }

    # ランキング生成
    if correlation_results:
        significant_correlations = [
            (name, info) for name, info in correlation_results if info["significance"] == "significant"
        ]
        significant_correlations.sort(key=lambda x: x[1]["abs_correlation"], reverse=True)

        correlation_analysis["correlation_analysis"]["ranking"] = {
            "most_influential_sensors": [
                {
                    "sensor": name,
                    "correlation_coefficient": info["correlation_coefficient"],
                    "strength": info["strength"],
                    "direction": info["direction"],
                    "p_value": info["p_value"],
                    "unit": info["unit"],
                }
                for name, info in significant_correlations[:5]  # トップ5
            ],
            "summary": {
                "strongest_correlation": {
                    "sensor": significant_correlations[0][0] if significant_correlations else None,
                    "coefficient": significant_correlations[0][1]["correlation_coefficient"]
                    if significant_correlations
                    else 0,
                    "strength": significant_correlations[0][1]["strength"]
                    if significant_correlations
                    else "none",
                }
                if significant_correlations
                else None,
                "total_significant_correlations": len(significant_correlations),
                "sensors_analyzed": len(correlation_results),
            },
        }

    return correlation_analysis


def _calculate_trend_analysis(duty_cycles: list) -> dict[str, Any]:
    """トレンド分析の計算"""
    if len(duty_cycles) <= 10:
        return {}

    # 線形回帰によるトレンド
    x = np.arange(len(duty_cycles))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, duty_cycles)

    return {
        "trend_analysis": {
            "duty_cycle_trend": {
                "slope": float(slope),
                "r_squared": float(r_value**2),
                "p_value": float(p_value),
                "trend_direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
                "trend_strength": (
                    "strong" if abs(r_value) > 0.7 else "moderate" if abs(r_value) > 0.3 else "weak"
                ),
            },
        }
    }


def perform_statistical_analysis(data: list[dict[str, Any]]) -> dict[str, Any]:
    """統計分析を実行"""
    if not _ANALYSIS_AVAILABLE or not data:
        return {"error": "Analysis not available or no data"}

    try:
        # 基本データの抽出
        duty_cycles = [row["valve_duty_cycle_percentage"] for row in data]
        flow_values = [row["flow_value"] for row in data if row["flow_value"] is not None]
        temperatures = [row["temperature"] for row in data if row.get("temperature") is not None]
        humidity_values = [row["humidity"] for row in data if row.get("humidity") is not None]
        solar_radiation_values = [
            row["solar_radiation"] for row in data if row.get("solar_radiation") is not None
        ]

        # 各分析を実行
        stats_result = _calculate_basic_statistics(data)

        # フロー分析を追加
        flow_analysis = _calculate_flow_analysis(flow_values)
        stats_result.update(flow_analysis)

        # 環境分析を追加
        env_analysis = _calculate_environmental_analysis(
            solar_radiation_values, temperatures, humidity_values
        )
        stats_result.update(env_analysis)

        # 相関分析を追加
        correlation_analysis = _calculate_correlation_analysis(data, duty_cycles)
        stats_result.update(correlation_analysis)

        # トレンド分析を追加
        trend_analysis = _calculate_trend_analysis(duty_cycles)
        stats_result.update(trend_analysis)

        return stats_result

    except Exception as e:
        logger.exception("Error in statistical analysis")
        return {"error": f"Statistical analysis failed: {e!s}"}


def _prepare_features(data: list[dict[str, Any]]) -> tuple[list, list]:
    """異常検知用の特徴量を準備"""
    features = []
    timestamps = []

    for row in data:
        if row["flow_value"] is not None:
            feature_row = [
                row["valve_duty_cycle_percentage"],
                row["flow_value"],
                row["valve_operations"],
                row["sensor_reads"],
                row["errors"],
            ]

            # センサーデータを追加
            feature_row.append(row.get("solar_radiation", 0))
            feature_row.append(row.get("temperature", 25))

            features.append(feature_row)
            timestamps.append(row["timestamp"])

    return features, timestamps


def _detect_anomalies(features_scaled: np.ndarray, timestamps: list, features: list) -> tuple[list, dict]:
    """異常検知の実行"""
    # Isolation Forest による異常検知
    iso_forest = IsolationForest(contamination=0.1, random_state=42)
    anomaly_scores = iso_forest.fit_predict(features_scaled)
    anomaly_scores_continuous = iso_forest.decision_function(features_scaled)

    # DBSCAN によるクラスタリング
    dbscan = DBSCAN(eps=0.5, min_samples=3)
    cluster_labels = dbscan.fit_predict(features_scaled)

    # 異常点の特定
    anomalies = []
    for i, (score, continuous_score) in enumerate(
        zip(anomaly_scores, anomaly_scores_continuous, strict=True)
    ):
        if score == -1:  # 異常点
            anomalies.append(
                {
                    "timestamp": timestamps[i],
                    "index": i,
                    "anomaly_score": float(continuous_score),
                    "features": {
                        "duty_cycle": float(features[i][0]),
                        "flow_value": float(features[i][1]),
                        "valve_operations": int(features[i][2]),
                        "sensor_reads": int(features[i][3]),
                        "errors": int(features[i][4]),
                        "solar_radiation": float(features[i][5]) if len(features[i]) > 5 else None,
                        "temperature": float(features[i][6]) if len(features[i]) > 6 else None,
                    },
                    "cluster": int(cluster_labels[i]) if cluster_labels[i] != -1 else None,
                }
            )

    return anomalies, {"cluster_labels": cluster_labels, "features_array": np.array(features)}


def _calculate_cluster_stats(cluster_labels: np.ndarray, features_array: np.ndarray) -> dict:
    """クラスター統計の計算"""
    unique_clusters = set(cluster_labels[cluster_labels != -1])
    cluster_stats = {}
    for cluster_id in unique_clusters:
        cluster_mask = cluster_labels == cluster_id
        cluster_features = features_array[cluster_mask]
        cluster_stats[f"cluster_{cluster_id}"] = {
            "size": int(np.sum(cluster_mask)),
            "duty_cycle_mean": float(np.mean(cluster_features[:, 0])),
            "flow_value_mean": float(np.mean(cluster_features[:, 1])),
        }
    return cluster_stats


def perform_anomaly_detection(data: list[dict[str, Any]]) -> dict[str, Any]:
    """機械学習による異常検知"""
    if not _ANALYSIS_AVAILABLE or len(data) < 10:
        return {"error": "Analysis not available or insufficient data (need at least 10 records)"}

    try:
        # 特徴量の準備
        features, timestamps = _prepare_features(data)

        if len(features) < 10:
            return {"error": "Insufficient data with flow values for anomaly detection"}

        features_array = np.array(features)

        # 特徴量の正規化
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features_array)

        # 異常検知実行
        anomalies, cluster_data = _detect_anomalies(features_scaled, timestamps, features)
        cluster_stats = _calculate_cluster_stats(
            cluster_data["cluster_labels"], cluster_data["features_array"]
        )

        return {
            "summary": {
                "total_points": len(features),
                "anomalies_detected": len(anomalies),
                "anomaly_rate": len(anomalies) / len(features),
                "clusters_found": len(
                    set(cluster_data["cluster_labels"][cluster_data["cluster_labels"] != -1])
                ),
                "noise_points": int(np.sum(cluster_data["cluster_labels"] == -1)),
            },
            "anomalies": anomalies[-20:],  # 最新20件の異常
            "cluster_statistics": cluster_stats,
            "feature_importance": {
                "duty_cycle": {
                    "mean": float(np.mean(features_array[:, 0])),
                    "std": float(np.std(features_array[:, 0])),
                },
                "flow_value": {
                    "mean": float(np.mean(features_array[:, 1])),
                    "std": float(np.std(features_array[:, 1])),
                },
                "valve_operations": {
                    "mean": float(np.mean(features_array[:, 2])),
                    "std": float(np.std(features_array[:, 2])),
                },
                "sensor_reads": {
                    "mean": float(np.mean(features_array[:, 3])),
                    "std": float(np.std(features_array[:, 3])),
                },
                "errors": {
                    "mean": float(np.mean(features_array[:, 4])),
                    "std": float(np.std(features_array[:, 4])),
                },
                "solar_radiation": {
                    "mean": float(np.mean(features_array[:, 5])),
                    "std": float(np.std(features_array[:, 5])),
                }
                if features_array.shape[1] > 5
                else None,
                "temperature": {
                    "mean": float(np.mean(features_array[:, 6])),
                    "std": float(np.std(features_array[:, 6])),
                }
                if features_array.shape[1] > 6
                else None,
            },
        }

    except Exception as e:
        logger.exception("Error in anomaly detection")
        return {"error": f"Anomaly detection failed: {e!s}"}


def perform_predictive_analysis(data: list[dict[str, Any]]) -> dict[str, Any]:
    """予測分析"""
    if not _ANALYSIS_AVAILABLE or len(data) < 20:
        return {"error": "Analysis not available or insufficient data (need at least 20 records)"}

    try:
        # 時系列データの準備
        timestamps = np.array([row["timestamp"] for row in data])
        duty_cycles = np.array([row["valve_duty_cycle_percentage"] for row in data])
        valve_operations = np.array([row["valve_operations"] for row in data])

        # 時間軸を正規化（開始時点を0とする）
        time_normalized = (timestamps - timestamps[0]) / 3600  # 時間単位

        # 次の動作予測（簡単な線形外挿）
        if len(duty_cycles) >= 5:
            # 最近のトレンドを使用
            recent_time = time_normalized[-5:]
            recent_duty = duty_cycles[-5:]

            if len(recent_time) > 1:
                slope, intercept, r_value, p_value, std_err = stats.linregress(recent_time, recent_duty)

                # 1時間後の予測
                next_hour = time_normalized[-1] + 1
                predicted_duty_cycle = slope * next_hour + intercept
                prediction_confidence = abs(r_value)

        # バルブ操作頻度の分析
        if len(valve_operations) > 1:
            operation_diffs = np.diff(valve_operations)
            operation_times = time_normalized[1:]  # diffなので1つ短くなる

            # 操作頻度のピーク時間帯分析
            if len(operation_times) >= 10:
                # 24時間周期での分析（時間があれば）
                hours_in_day = np.array([(t % 24) for t in operation_times])
                hour_bins = np.arange(0, 25, 1)
                hour_counts, _ = np.histogram(hours_in_day, bins=hour_bins, weights=operation_diffs)
                peak_hour = int(np.argmax(hour_counts))

        # 故障予測（エラー率の傾向）
        errors = np.array([row["errors"] for row in data])
        if len(errors) > 10:
            error_diffs = np.diff(errors)
            error_rate_trend = np.polyfit(range(len(error_diffs)), error_diffs, 1)[0]

        # メンテナンス推奨時期
        total_operations = valve_operations[-1] if len(valve_operations) > 0 else 0
        maintenance_threshold = 10000  # 仮の閾値
        operations_to_maintenance = max(0, maintenance_threshold - total_operations)

        return {
            "duty_cycle_prediction": {
                "next_hour_predicted": float(predicted_duty_cycle)
                if "predicted_duty_cycle" in locals()
                else None,
                "confidence": float(prediction_confidence) if "prediction_confidence" in locals() else 0,
                "trend_slope": float(slope) if "slope" in locals() else 0,
                "r_squared": float(r_value**2) if "r_value" in locals() else 0,
            },
            "operation_pattern": {
                "peak_activity_hour": int(peak_hour) if "peak_hour" in locals() else None,
                "average_operations_per_hour": float(np.mean(operation_diffs))
                if "operation_diffs" in locals() and len(operation_diffs) > 0
                else 0,
            },
            "maintenance_forecast": {
                "total_operations": int(total_operations),
                "operations_until_maintenance": int(operations_to_maintenance),
                "estimated_days_to_maintenance": float(
                    operations_to_maintenance / (np.mean(operation_diffs) * 24)
                )
                if "operation_diffs" in locals() and len(operation_diffs) > 0 and np.mean(operation_diffs) > 0
                else None,
            },
            "reliability_analysis": {
                "error_rate_trend": float(error_rate_trend) if "error_rate_trend" in locals() else 0,
                "predicted_error_increase": "increasing"
                if "error_rate_trend" in locals() and error_rate_trend > 0
                else "stable",
                "reliability_score": float(max(0, 1 - (errors[-1] / max(1, valve_operations[-1]))))
                if len(errors) > 0 and len(valve_operations) > 0
                else 1.0,
            },
        }

    except Exception as e:
        logger.exception("Error in predictive analysis")
        return {"error": f"Predictive analysis failed: {e!s}"}


def _generate_executive_summary(result: dict[str, Any]) -> dict[str, Any]:
    """エグゼクティブサマリー生成"""
    if "statistical_analysis" not in result or "anomaly_detection" not in result:
        return {}

    anomaly_count = result["anomaly_detection"].get("summary", {}).get("anomalies_detected", 0)
    total_points = result["anomaly_detection"].get("summary", {}).get("total_points", 0)

    summary = {
        "system_health": "good"
        if anomaly_count / max(1, total_points) < 0.05
        else "warning"
        if anomaly_count / max(1, total_points) < 0.1
        else "critical",
        "data_quality": "high" if total_points > 100 else "medium" if total_points > 20 else "low",
        "analysis_confidence": "high"
        if _ANALYSIS_AVAILABLE and total_points > 100
        else "medium"
        if total_points > 20
        else "low",
        "key_insights": [],
    }

    # 主要な洞察を生成
    stats_data = result.get("statistical_analysis", {})

    # デューティサイクル分析
    if "duty_cycle_analysis" in stats_data:
        mean_duty = stats_data["duty_cycle_analysis"]["mean"]
        if mean_duty > 80:
            summary["key_insights"].append("High duty cycle detected - consider system optimization")
        elif mean_duty < 10:
            summary["key_insights"].append("Low duty cycle - system may be underutilized")

    # エラー分析
    if "error_analysis" in stats_data and stats_data["error_analysis"]["total_errors"] > 0:
        summary["key_insights"].append(f"Error count: {stats_data['error_analysis']['total_errors']}")

    # 相関分析の洞察
    _add_correlation_insights(stats_data, summary)

    # 環境データの洞察
    _add_environmental_insights(stats_data, summary)

    return summary


def _add_correlation_insights(stats_data: dict[str, Any], summary: dict[str, Any]) -> None:
    """相関分析の洞察を追加"""
    if "correlation_analysis" not in stats_data:
        return

    ranking = stats_data["correlation_analysis"].get("ranking")
    if not ranking or not ranking["summary"]["strongest_correlation"]:
        return

    strongest = ranking["summary"]["strongest_correlation"]
    sensor_name = strongest["sensor"]
    correlation_coef = strongest["coefficient"]
    strength = strongest["strength"]

    # センサー名を日本語に変換
    sensor_names_jp = {
        "solar_radiation": "日射量",
        "temperature": "温度",
        "humidity": "湿度",
        "lux": "照度",
        "power_consumption": "電力消費",
        "rain_amount": "雨量",
        "flow_value": "流量",
    }
    sensor_jp = sensor_names_jp.get(sensor_name, sensor_name)

    insight = f"Most influential factor: {sensor_jp} ({strength} correlation, r={correlation_coef:.3f})"
    summary["key_insights"].append(insight)

    # 上位3つのセンサーを表示
    top_sensors = ranking["most_influential_sensors"][:3]
    if len(top_sensors) > 1:
        top_names = [sensor_names_jp.get(s["sensor"], s["sensor"]) for s in top_sensors]
        summary["key_insights"].append(f"Top correlations: {', '.join(top_names)}")

    # 有意な相関の総数
    total_significant = ranking["summary"]["total_significant_correlations"]
    if total_significant > 0:
        summary["key_insights"].append(f"Found {total_significant} significant correlations with duty cycle")


def _add_environmental_insights(stats_data: dict[str, Any], summary: dict[str, Any]) -> None:
    """環境データの洞察を追加"""
    if "environmental_analysis" not in stats_data:
        return

    env_data = stats_data["environmental_analysis"]

    # 日射量分析
    if "solar_radiation" in env_data:
        solar_mean = env_data["solar_radiation"]["mean"]
        solar_max = env_data["solar_radiation"]["max"]
        if solar_mean > 500:  # 高日射量
            summary["key_insights"].append(f"High solar radiation detected (avg: {solar_mean:.0f} W/m²)")
        if solar_max > 1000:  # 非常に高い日射量
            summary["key_insights"].append(
                f"Peak solar radiation: {solar_max:.0f} W/m² - may require enhanced cooling"
            )

    # 温度分析
    if "temperature" in env_data:
        temp_mean = env_data["temperature"]["mean"]
        temp_max = env_data["temperature"]["max"]
        if temp_mean > 30:  # 高温
            summary["key_insights"].append(f"High average temperature: {temp_mean:.1f}°C")
        if temp_max > 35:  # 非常に高温
            summary["key_insights"].append(f"Peak temperature: {temp_max:.1f}°C - monitor for overheating")


@blueprint.route("/api/metrics/analysis", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_metrics_analysis():
    """メトリクス分析結果をJSON形式で返す"""
    try:
        # クエリパラメータ
        hours = int(flask.request.args.get("hours", 48))  # デフォルト48時間
        analysis_type = flask.request.args.get("type", "all")  # all, stats, anomaly, predict

        # データベースからデータを取得
        historical_data = get_metrics_from_db(hours)

        if not historical_data:
            return flask.jsonify(
                {
                    "error": "No historical data available",
                    "timestamp": time.time(),
                    "analysis_available": _ANALYSIS_AVAILABLE,
                }
            ), 404

        result = {
            "timestamp": time.time(),
            "analysis_period_hours": hours,
            "data_points": len(historical_data),
            "analysis_available": _ANALYSIS_AVAILABLE,
        }

        # 分析タイプに応じて実行
        if analysis_type in ["all", "stats"]:
            result["statistical_analysis"] = perform_statistical_analysis(historical_data)

        if analysis_type in ["all", "anomaly"]:
            result["anomaly_detection"] = perform_anomaly_detection(historical_data)

        if analysis_type in ["all", "predict"]:
            result["predictive_analysis"] = perform_predictive_analysis(historical_data)

        # 概要情報
        if "statistical_analysis" in result and "anomaly_detection" in result:
            result["executive_summary"] = _generate_executive_summary(result)

        return flask.jsonify(result)

    except Exception as e:
        logger.exception("Error generating metrics analysis")
        return flask.jsonify(
            {
                "error": str(e),
                "timestamp": time.time(),
                "analysis_available": _ANALYSIS_AVAILABLE,
            }
        ), 500


def _calculate_sensor_correlation(
    sensor_name: str, sensor_jp: str, unit: str, historical_data: list
) -> dict[str, Any] | None:
    """個別センサーの相関分析"""
    sensor_data = [row.get(sensor_name) for row in historical_data if row.get(sensor_name) is not None]

    if len(sensor_data) < 10:
        return None

    sensor_duty_pairs = []
    for row in historical_data:
        sensor_value = row.get(sensor_name)
        duty_value = row.get("valve_duty_cycle_percentage")
        if sensor_value is not None and duty_value is not None:
            sensor_duty_pairs.append((sensor_value, duty_value))

    if len(sensor_duty_pairs) < 10:
        return None

    sensor_vals, duty_vals = zip(*sensor_duty_pairs, strict=True)
    correlation_coef, correlation_p_value = stats.pearsonr(sensor_vals, duty_vals)

    return {
        "sensor_name": sensor_name,
        "sensor_name_jp": sensor_jp,
        "unit": unit,
        "correlation_coefficient": float(correlation_coef),
        "p_value": float(correlation_p_value),
        "significance": "significant" if correlation_p_value < 0.05 else "not_significant",
        "strength": (
            "strong" if abs(correlation_coef) > 0.7 else "moderate" if abs(correlation_coef) > 0.3 else "weak"
        ),
        "direction": "positive" if correlation_coef > 0 else "negative",
        "data_points": len(sensor_duty_pairs),
        "abs_correlation": abs(correlation_coef),
        "sensor_stats": {
            "mean": float(np.mean(sensor_vals)),
            "std": float(np.std(sensor_vals)),
            "min": float(np.min(sensor_vals)),
            "max": float(np.max(sensor_vals)),
        },
        "duty_cycle_stats": {
            "mean": float(np.mean(duty_vals)),
            "std": float(np.std(duty_vals)),
            "min": float(np.min(duty_vals)),
            "max": float(np.max(duty_vals)),
        },
    }


def _validate_correlation_request(
    historical_data: list, *, analysis_available: bool
) -> tuple[dict | None, int]:
    """相関分析リクエストの検証"""
    if not historical_data:
        return {
            "error": "No historical data available",
            "timestamp": time.time(),
            "analysis_available": analysis_available,
        }, 404

    if not analysis_available:
        return {
            "error": "Statistical analysis libraries not available",
            "timestamp": time.time(),
            "analysis_available": False,
        }, 503

    duty_cycles = [row["valve_duty_cycle_percentage"] for row in historical_data]
    if len(duty_cycles) < 10:
        return {
            "error": "Insufficient data for correlation analysis (need at least 10 points)",
            "timestamp": time.time(),
            "data_points": len(duty_cycles),
        }, 400

    return None, 200


def _calculate_sensor_correlation_info(
    sensor_name: str, sensor_jp: str, unit: str, historical_data: list
) -> dict | None:
    """個別センサーの相関情報を計算"""
    sensor_duty_pairs = [
        (row.get(sensor_name), row.get("valve_duty_cycle_percentage"))
        for row in historical_data
        if row.get(sensor_name) is not None and row.get("valve_duty_cycle_percentage") is not None
    ]

    if len(sensor_duty_pairs) < 10:
        return None

    sensor_vals, duty_vals = zip(*sensor_duty_pairs, strict=True)
    correlation_coef, correlation_p_value = stats.pearsonr(sensor_vals, duty_vals)

    return {
        "sensor_name": sensor_name,
        "sensor_name_jp": sensor_jp,
        "unit": unit,
        "correlation_coefficient": float(correlation_coef),
        "p_value": float(correlation_p_value),
        "significance": "significant" if correlation_p_value < 0.05 else "not_significant",
        "strength": (
            "strong" if abs(correlation_coef) > 0.7 else "moderate" if abs(correlation_coef) > 0.3 else "weak"
        ),
        "direction": "positive" if correlation_coef > 0 else "negative",
        "data_points": len(sensor_duty_pairs),
        "abs_correlation": abs(correlation_coef),
        "sensor_stats": {
            "mean": float(np.mean(sensor_vals)),
            "std": float(np.std(sensor_vals)),
            "min": float(np.min(sensor_vals)),
            "max": float(np.max(sensor_vals)),
        },
        "duty_cycle_stats": {
            "mean": float(np.mean(duty_vals)),
            "std": float(np.std(duty_vals)),
            "min": float(np.min(duty_vals)),
            "max": float(np.max(duty_vals)),
        },
    }


def _create_correlation_ranking(correlation_results: list) -> dict:
    """相関分析のランキングを作成"""
    significant_correlations = [
        (name, info) for name, info in correlation_results if info["significance"] == "significant"
    ]
    significant_correlations.sort(key=lambda x: x[1]["abs_correlation"], reverse=True)

    return {
        "by_correlation_strength": [
            {
                "rank": i + 1,
                "sensor": name,
                "sensor_name_jp": info["sensor_name_jp"],
                "correlation_coefficient": info["correlation_coefficient"],
                "abs_correlation": info["abs_correlation"],
                "strength": info["strength"],
                "direction": info["direction"],
                "p_value": info["p_value"],
                "unit": info["unit"],
            }
            for i, (name, info) in enumerate(significant_correlations)
        ],
        "summary": {
            "strongest_correlation": {
                "sensor": significant_correlations[0][0] if significant_correlations else None,
                "sensor_name_jp": significant_correlations[0][1]["sensor_name_jp"]
                if significant_correlations
                else None,
                "coefficient": significant_correlations[0][1]["correlation_coefficient"]
                if significant_correlations
                else 0,
                "strength": significant_correlations[0][1]["strength"]
                if significant_correlations
                else "none",
            }
            if significant_correlations
            else None,
            "total_sensors_analyzed": len(correlation_results),
            "significant_correlations": len(significant_correlations),
            "insignificant_correlations": len(correlation_results) - len(significant_correlations),
        },
    }


@blueprint.route("/api/metrics/correlation", methods=["GET"])
@my_lib.flask_util.support_jsonp
def get_correlation_analysis():
    """センサーデータとデューティサイクルの相関分析専用エンドポイント"""
    try:
        # クエリパラメータ
        hours = int(flask.request.args.get("hours", 48))
        sensor_type = flask.request.args.get("sensor")

        # データベースからデータを取得
        historical_data = get_metrics_from_db(hours)

        # 基本検証
        error_response, status_code = _validate_correlation_request(
            historical_data, analysis_available=_ANALYSIS_AVAILABLE
        )
        if error_response:
            return flask.jsonify(error_response), status_code

        result = {
            "timestamp": time.time(),
            "analysis_period_hours": hours,
            "data_points": len(historical_data),
            "correlations": {},
            "ranking": {},
        }

        # センサーデータのリスト
        sensor_datasets = [
            ("solar_radiation", "日射量", "W/m²"),
            ("temperature", "温度", "°C"),
            ("humidity", "湿度", "%"),
            ("lux", "照度", "lux"),
            ("power_consumption", "電力消費", "W"),
            ("rain_amount", "雨量", "mm/h"),
            ("flow_value", "流量", "L/min"),
        ]

        # 特定のセンサーが指定された場合はそれのみ分析
        if sensor_type:
            sensor_datasets = [(s, jp, u) for s, jp, u in sensor_datasets if s == sensor_type]

        correlation_results = []
        for sensor_name, sensor_jp, unit in sensor_datasets:
            correlation_info = _calculate_sensor_correlation_info(
                sensor_name, sensor_jp, unit, historical_data
            )
            if correlation_info:
                result["correlations"][sensor_name] = correlation_info
                correlation_results.append((sensor_name, correlation_info))

        # ランキング作成
        if correlation_results:
            result["ranking"] = _create_correlation_ranking(correlation_results)

        return flask.jsonify(result)

    except Exception as e:
        logger.exception("Error in correlation analysis")
        return flask.jsonify(
            {
                "error": str(e),
                "timestamp": time.time(),
                "analysis_available": _ANALYSIS_AVAILABLE,
            }
        ), 500
