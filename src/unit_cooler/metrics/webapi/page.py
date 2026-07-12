"""
室外機冷却システムメトリクス表示ページ

冷却モード、Duty比、環境要因の統計情報とグラフを表示する Web ページを提供します。
HTML/CSS/JS は templates/ と static/ 配下の静的ファイルで管理し、
このモジュールはルート定義とデータ準備・統計ロジックのみを担当します。
"""

import datetime
import logging
import pathlib
import threading
import time
from dataclasses import dataclass
from typing import Any

import flask

import unit_cooler.config
import unit_cooler.const
import unit_cooler.metrics.collector
import unit_cooler.metrics.energy

logger = logging.getLogger(__name__)

blueprint = flask.Blueprint(
    "metrics",
    __name__,
    url_prefix=unit_cooler.const.URL_PREFIX,
    template_folder="templates",
    static_folder="static",
    static_url_path="/metrics/static",
)

# Web UI 用の静的ファイル配信 blueprint。
# メトリクスページは Web UI のプロキシ（/api/proxy/html/api/metrics）経由でも表示されるが、
# ページ内の url_for("metrics.static", ...) は Actuator 上の絶対パスを生成するため、
# Web UI 側にも同じパスで JS/CSS/favicon を配信するルートが必要になる。
static_blueprint = flask.Blueprint(
    "metrics-static",
    __name__,
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

# 省エネ効果分析のキャッシュ TTL〔秒〕（InfluxDB からの取得と集計が重いため）
_ENERGY_CACHE_TTL_SEC = 3600.0
_energy_cache: tuple[float, unit_cooler.metrics.energy.EnergyAnalysis] | None = None
_energy_cache_lock = threading.Lock()


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

        config = flask.current_app.config["CONFIG"]
        period = collector.get_period_summary()
        stats = generate_statistics(
            collector.get_statistics_summary(), collector.count_errors(), period.total_days
        )

        return flask.render_template(
            "metrics.html",
            period_text=format_period_text(period),
            stats=format_statistics(stats),
            energy=format_energy(get_energy_analysis(config, collector)),
            # NOTE: 相対パスにすることで、直接アクセス（/unit-cooler/api/metrics）と
            # Web UI プロキシ経由（/unit-cooler/api/proxy/html/api/metrics）の両方で解決できる
            data_url="metrics/data",
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

        config = flask.current_app.config["CONFIG"]
        timeseries_rows = collector.get_timeseries_data(TIMESERIES_MAX_POINTS, TIMESERIES_TARGET_POINTS)

        return flask.jsonify(
            {
                **prepare_boxplot_data(collector),
                "timeseries": prepare_timeseries_data(timeseries_rows),
                "correlation": prepare_correlation_data(collector),
                "energy_savings": get_energy_analysis(config, collector).to_chart_dict(),
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
    summary: unit_cooler.metrics.collector.StatisticsSummary, error_count: int, total_days: int
) -> dict:
    """SQL 側で集計したサマリーから統計情報を生成"""
    return {
        "total_days": total_days,
        "cooling_mode_avg": summary.cooling_mode_avg,
        "duty_ratio_avg": summary.duty_ratio_avg,
        "valve_operations_total": summary.valve_operations_total,
        "error_total": error_count,
        "data_points": summary.data_points,
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


def prepare_timeseries_data(aggregated_rows: list[dict]) -> list[dict]:
    """時系列チャート用データを準備

    aggregated_rows は MetricsCollector.get_timeseries_data() で
    SQL 側で平均化済みのデータ（古い順）を渡す前提。
    ここではタイムスタンプの表示用フォーマットのみを行う。
    """
    timeseries_data = []
    for data in aggregated_rows:
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


def prepare_correlation_data(
    collector: unit_cooler.metrics.collector.MetricsCollector,
) -> dict[str, dict[str, list]]:
    """散布図用データを準備

    ペアの両カラムが non-NULL の行だけを SQL 側で抽出し {x: [], y: []} 形式で返す。
    """
    result = {}
    for key, x_column, y_column in CORRELATION_PAIRS:
        x_values, y_values = collector.get_correlation_pairs(x_column, y_column)
        result[key] = {"x": x_values, "y": y_values}
    return result


@dataclass(frozen=True)
class EnergyView:
    """省エネ効果セクションのテンプレート表示用データ"""

    valid: bool
    note: str
    saved_energy: str = ""
    saved_cost: str = ""
    water_cost: str = ""
    net_benefit: str = ""


def format_energy(analysis: unit_cooler.metrics.energy.EnergyAnalysis) -> EnergyView:
    """省エネ効果の推定結果をテンプレート表示用に変換"""
    if not analysis.valid:
        return EnergyView(valid=False, note=analysis.message)

    unit_price = unit_cooler.metrics.energy.ELECTRICITY_UNIT_PRICE
    return EnergyView(
        valid=True,
        note=(
            f"{analysis.message}。"
            f"散水あり {analysis.watering_hours:,.0f} 時間 / 散水量 {analysis.water_amount:,.0f} L、"
            f"電気単価 {unit_price:.0f} 円/kWh で換算。"
        ),
        saved_energy=f"{analysis.saved_energy_kwh:,.1f} kWh",
        saved_cost=f"{analysis.saved_cost:,.0f} 円",
        water_cost=f"{analysis.water_cost:,.0f} 円",
        net_benefit=f"{analysis.net_benefit:+,.0f} 円",
    )


def get_energy_analysis(
    config: unit_cooler.config.Config, collector: unit_cooler.metrics.collector.MetricsCollector
) -> unit_cooler.metrics.energy.EnergyAnalysis:
    """省エネ効果分析を TTL キャッシュ付きで取得する

    InfluxDB からの取得と集計が重いため、結果を _ENERGY_CACHE_TTL_SEC の間
    キャッシュする（失敗結果もキャッシュして外部サービスへの連続アクセスを避ける）。
    """
    global _energy_cache

    with _energy_cache_lock:
        if _energy_cache is not None and time.monotonic() - _energy_cache[0] < _ENERGY_CACHE_TTL_SEC:
            return _energy_cache[1]

        try:
            analysis = unit_cooler.metrics.energy.collect_energy_analysis(config, collector)
        except Exception:
            # NOTE: InfluxDB クライアントは接続・認証・パース等の多様な例外を送出し得るため、
            # I/O 境界としてここで包括的に受けてダッシュボード全体が落ちるのを防ぐ
            logger.exception("省エネ効果の分析に失敗しました")
            analysis = unit_cooler.metrics.energy.insufficient_analysis("分析処理でエラーが発生しました")

        _energy_cache = (time.monotonic(), analysis)
        return analysis
