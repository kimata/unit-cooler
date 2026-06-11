"""
室外機冷却システムメトリクス表示ページ

冷却モード、Duty比、環境要因の統計情報とグラフを表示する Web ページを提供します。
HTML/CSS/JS は templates/ と static/ 配下の静的ファイルで管理し、
このモジュールはルート定義とデータ準備・統計ロジックのみを担当します。
"""

import datetime
import logging
import pathlib
from dataclasses import dataclass
from typing import Any

import flask

import unit_cooler.const
import unit_cooler.metrics.collector

logger = logging.getLogger(__name__)

blueprint = flask.Blueprint(
    "metrics",
    __name__,
    url_prefix=unit_cooler.const.URL_PREFIX,
    template_folder="templates",
    static_folder="static",
    static_url_path="/metrics/static",
)

# 時系列チャートで扱うカラム
TIMESERIES_COLUMNS = [
    "cooling_mode",
    "duty_ratio",
    "temperature",
    "humidity",
    "lux",
    "solar_radiation",
    "rain_amount",
]

# 散布図のペア定義 (JSON キー, X カラム, Y カラム)
CORRELATION_PAIRS = [
    ("temp_cooling", "temperature", "cooling_mode"),
    ("humidity_duty", "humidity", "duty_ratio"),
    ("solar_cooling", "solar_radiation", "cooling_mode"),
    ("lux_duty", "lux", "duty_ratio"),
]

# 箱ヒゲ図の定義 (JSON キー, カラム, 表示倍率)
BOXPLOT_COLUMNS = [
    ("boxplot_cooling_mode", "cooling_mode", 1.0),
    ("boxplot_duty_ratio", "duty_ratio", 100.0),
    ("boxplot_valve_ops", "valve_operations", 1.0),
]

TIMESERIES_MAX_POINTS = 144000  # 直近 100 日分（分単位）
TIMESERIES_TARGET_POINTS = 1000  # 平均化後の目標ポイント数


@dataclass(frozen=True)
class BoxplotStats:
    """箱ヒゲ図統計データ"""

    min: float
    q1: float
    median: float
    q3: float
    max: float
    outliers: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "min": self.min,
            "q1": self.q1,
            "median": self.median,
            "q3": self.q3,
            "max": self.max,
            "outliers": self.outliers,
        }


def normalize_timestamp(timestamp: str | datetime.datetime) -> datetime.datetime:
    """ISO 8601 文字列タイムスタンプを datetime に正規化する"""
    if isinstance(timestamp, datetime.datetime):
        return timestamp
    return datetime.datetime.fromisoformat(timestamp)


def _resolve_collector() -> tuple[unit_cooler.metrics.collector.MetricsCollector | None, str | None]:
    """設定からメトリクスコレクターを解決する。失敗時は (None, エラーメッセージ) を返す"""
    config = flask.current_app.config["CONFIG"]
    db_path = config.actuator.metrics.data

    if not db_path:
        return None, "メトリクス設定が見つかりません"
    if not pathlib.Path(db_path).exists():
        return None, f"メトリクスデータベースが見つかりません: {db_path}"

    return unit_cooler.metrics.collector.get_metrics_collector(db_path), None


@blueprint.route("/api/metrics", methods=["GET"])
def metrics_view():
    """メトリクスダッシュボードページを表示"""
    try:
        collector, error = _resolve_collector()
        if collector is None:
            return flask.Response(
                f"<html><body><h1>{error}</h1></body></html>", mimetype="text/html", status=503
            )

        minute_data = collector.get_minute_data()
        hourly_data = collector.get_hourly_data()
        period = collector.get_period_summary()
        stats = generate_statistics(minute_data, hourly_data, collector.count_errors(), period.total_days)

        return flask.render_template(
            "metrics.html",
            period_text=format_period_text(period),
            stats=format_statistics(stats),
            data_url=flask.url_for("metrics.metrics_data"),
        )
    except Exception as e:
        logger.exception("メトリクス表示の生成エラー")
        return flask.Response(f"エラー: {e!s}", mimetype="text/plain", status=500)


@blueprint.route("/api/metrics/data", methods=["GET"])
def metrics_data():
    """チャート描画用データを JSON で返す"""
    try:
        collector, error = _resolve_collector()
        if collector is None:
            return flask.jsonify({"error": error}), 503

        minute_data = collector.get_minute_data()

        return flask.jsonify(
            {
                **prepare_boxplot_data(collector),
                "timeseries": prepare_timeseries_data(minute_data),
                "correlation": prepare_correlation_data(minute_data),
            }
        )
    except Exception as e:
        logger.exception("メトリクスデータの生成エラー")
        return flask.jsonify({"error": str(e)}), 500


@blueprint.route("/favicon.ico", methods=["GET"])
def favicon():
    """メトリクスダッシュボード用 favicon.ico を返す"""
    static_folder = blueprint.static_folder
    if static_folder is None:
        return flask.Response("", status=500)
    return flask.send_from_directory(static_folder, "favicon.ico", mimetype="image/x-icon", max_age=3600)


def format_period_text(period: unit_cooler.metrics.collector.PeriodSummary) -> str:
    """データ収集期間の説明テキストを生成"""
    if period.start is None or period.end is None:
        return "データなし"

    span_days = (period.end - period.start).days + 1
    return f"過去{span_days}日間（{period.start.strftime('%Y年%m月%d日')}〜）の冷却システム統計"


def generate_statistics(
    minute_data: list[dict], hourly_data: list[dict], error_count: int, total_days: int
) -> dict:
    """メトリクスデータから統計情報を生成"""
    cooling_modes = [d["cooling_mode"] for d in minute_data if d.get("cooling_mode") is not None]
    duty_ratios = [d["duty_ratio"] for d in minute_data if d.get("duty_ratio") is not None]

    return {
        "total_days": total_days,
        "cooling_mode_avg": sum(cooling_modes) / len(cooling_modes) if cooling_modes else None,
        "duty_ratio_avg": sum(duty_ratios) / len(duty_ratios) if duty_ratios else None,
        "valve_operations_total": sum(d.get("valve_operations") or 0 for d in hourly_data),
        "error_total": error_count,
        "data_points": len(minute_data),
    }


def format_statistics(stats: dict) -> dict[str, str]:
    """統計情報をテンプレート表示用文字列に変換"""
    cooling_avg = stats["cooling_mode_avg"]
    duty_avg = stats["duty_ratio_avg"]

    return {
        "cooling_mode_avg": "N/A" if cooling_avg is None else f"{cooling_avg:.2f}",
        "duty_ratio_avg": "N/A" if duty_avg is None else f"{duty_avg * 100:.1f}%",
        "valve_operations_total": f"{stats['valve_operations_total']:,}",
        "error_total": f"{stats['error_total']:,}",
        "data_points": f"{stats['data_points']:,}",
        "total_days": f"{stats['total_days']:,}",
    }


def calculate_boxplot_stats(values: list[float]) -> BoxplotStats:
    """箱ヒゲ図用の統計データを計算"""
    if not values:
        return BoxplotStats(min=0, q1=0, median=0, q3=0, max=0, outliers=[])

    values_sorted = sorted(values)
    n = len(values_sorted)

    q1 = values_sorted[n // 4]
    median = values_sorted[n // 2]
    q3 = values_sorted[3 * n // 4]

    # IQR と外れ値を計算
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outliers = [v for v in values_sorted if v < lower_bound or v > upper_bound]

    # 外れ値を除いた最小値・最大値
    non_outliers = [v for v in values_sorted if lower_bound <= v <= upper_bound]
    min_val = min(non_outliers) if non_outliers else values_sorted[0]
    max_val = max(non_outliers) if non_outliers else values_sorted[-1]

    return BoxplotStats(min=min_val, q1=q1, median=median, q3=q3, max=max_val, outliers=outliers)


def prepare_boxplot_data(collector: unit_cooler.metrics.collector.MetricsCollector) -> dict[str, list]:
    """時間帯別の箱ヒゲ図データを準備"""
    result = {}
    for key, column, scale in BOXPLOT_COLUMNS:
        hourly_values: list[list[float]] = [[] for _ in range(24)]
        for hour, value in collector.get_hourly_values(column):
            if 0 <= hour < 24:
                hourly_values[hour].append(value * scale)

        result[key] = [
            {"x": f"{hour:02d}:00", "y": calculate_boxplot_stats(hourly_values[hour]).to_dict()}
            for hour in range(24)
        ]
    return result


def _average_chunk(chunk: list[dict]) -> dict:
    """チャンク内の数値カラムを平均化する"""
    averaged: dict[str, Any] = {"timestamp": chunk[0].get("timestamp")}
    for column in TIMESERIES_COLUMNS:
        values = [d[column] for d in chunk if d.get(column) is not None]
        averaged[column] = sum(values) / len(values) if values else None
    return averaged


def prepare_timeseries_data(minute_data: list[dict]) -> list[dict]:
    """時系列チャート用データを準備（直近 100 日分）

    minute_data は新しい順（DESC）で渡される前提。
    """
    recent_data = list(reversed(minute_data[:TIMESERIES_MAX_POINTS]))

    # データポイント数が多い場合は平均化して間引く
    if len(recent_data) > TIMESERIES_TARGET_POINTS:
        chunk_size = len(recent_data) // TIMESERIES_TARGET_POINTS
        recent_data = [
            _average_chunk(recent_data[i : i + chunk_size]) for i in range(0, len(recent_data), chunk_size)
        ]

    timeseries_data = []
    for data in recent_data:
        if not data.get("timestamp"):
            continue

        try:
            label = normalize_timestamp(data["timestamp"]).strftime("%m/%d %H:%M")
        except (ValueError, TypeError):
            logger.debug("Failed to parse timestamp for time series formatting")
            label = str(data["timestamp"])

        entry: dict[str, Any] = {"timestamp": label}
        for column in TIMESERIES_COLUMNS:
            entry[column] = data.get(column)
        timeseries_data.append(entry)

    return timeseries_data


def prepare_correlation_data(minute_data: list[dict]) -> dict[str, dict[str, list]]:
    """散布図用データを準備

    ペアの両カラムが non-None の行だけを {x: [], y: []} 形式で返す。
    """
    result = {}
    for key, x_column, y_column in CORRELATION_PAIRS:
        x_values: list[float] = []
        y_values: list[float] = []
        for data in minute_data:
            x, y = data.get(x_column), data.get(y_column)
            if x is not None and y is not None:
                x_values.append(x)
                y_values.append(y)
        result[key] = {"x": x_values, "y": y_values}
    return result
