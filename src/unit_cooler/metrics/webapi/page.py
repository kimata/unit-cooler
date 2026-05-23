"""
室外機冷却システムメトリクス表示ページ

冷却モード、Duty比、環境要因の統計情報とグラフを表示するWebページを提供します。
"""

import datetime
import io
import json
import logging
from dataclasses import dataclass
from typing import Any

import flask
import my_lib.time
from PIL import Image, ImageDraw

import unit_cooler.const
import unit_cooler.metrics.collector

logger = logging.getLogger(__name__)


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


blueprint = flask.Blueprint("metrics", __name__, url_prefix=unit_cooler.const.URL_PREFIX)

TOKYO_TZ = my_lib.time.get_zoneinfo()


def normalize_timestamp(timestamp: str | datetime.datetime) -> datetime.datetime:
    """タイムスタンプを datetime に正規化する

    Args:
        timestamp: ISO形式文字列または datetime オブジェクト

    Returns:
        タイムゾーン付き datetime オブジェクト
    """
    if isinstance(timestamp, datetime.datetime):
        return timestamp

    # ISO形式（T区切り）
    if "T" in timestamp:
        return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    # スペース区切りの形式
    return datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TOKYO_TZ)


@blueprint.route("/api/metrics", methods=["GET"])
def metrics_view():
    """メトリクスダッシュボードページを表示"""
    try:
        # 設定からメトリクスデータパスを取得
        config = flask.current_app.config["CONFIG"]
        metrics_data_path = config.actuator.metrics.data

        # データベースファイルの存在確認
        if not metrics_data_path:
            return flask.Response(
                "<html><body><h1>メトリクス設定が見つかりません</h1>"
                "<p>config.yamlでactuator.metricsセクションが設定されていません。</p></body></html>",
                mimetype="text/html",
                status=503,
            )

        from pathlib import Path

        db_path = Path(metrics_data_path)
        if not db_path.exists():
            return flask.Response(
                f"<html><body><h1>メトリクスデータベースが見つかりません</h1>"
                f"<p>データベースファイル: {db_path}</p>"
                f"<p>システムが十分に動作してからメトリクスが生成されます。</p></body></html>",
                mimetype="text/html",
                status=503,
            )

        # メトリクス収集器を取得
        collector = unit_cooler.metrics.collector.get_metrics_collector(metrics_data_path)

        # 全期間のデータを取得（制限なし）
        end_time = my_lib.time.now()
        start_time = None  # 無制限

        minute_data = collector.get_minute_data(start_time, end_time, limit=None)
        hourly_data = collector.get_hourly_data(start_time, end_time, limit=None)
        error_data = collector.get_error_data(start_time, end_time, limit=None)

        # 統計データを生成
        stats = generate_statistics(minute_data, hourly_data, error_data)

        # データ期間情報を取得
        period_info = get_data_period_info(minute_data, hourly_data)

        # HTMLを生成
        html_content = generate_metrics_html(stats, minute_data, hourly_data, period_info)

        return flask.Response(html_content, mimetype="text/html")

    except Exception as e:
        logger.exception("メトリクス表示の生成エラー")
        return flask.Response(f"エラー: {e!s}", mimetype="text/plain", status=500)


@blueprint.route("/favicon.ico", methods=["GET"])
def favicon():
    """動的生成された室外機冷却システムメトリクス用favicon.icoを返す"""
    try:
        # 室外機冷却システムメトリクスアイコンを生成
        img = generate_cooler_metrics_icon()

        # ICO形式で出力
        output = io.BytesIO()
        img.save(output, format="ICO", sizes=[(32, 32)])
        output.seek(0)

        return flask.Response(
            output.getvalue(),
            mimetype="image/x-icon",
            headers={
                "Cache-Control": "public, max-age=3600",  # 1時間キャッシュ
                "Content-Type": "image/x-icon",
            },
        )
    except Exception:
        logger.exception("favicon生成エラー")
        return flask.Response("", status=500)


def generate_cooler_metrics_icon():
    """室外機冷却システムメトリクス用のアイコンを動的生成（アンチエイリアス対応）"""
    # アンチエイリアスのため4倍サイズで描画してから縮小
    scale = 4
    size = 32
    large_size = size * scale

    # 大きなサイズで描画
    img = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景円（冷却システムらしい青色）
    margin = 2 * scale
    draw.ellipse(
        [margin, margin, large_size - margin, large_size - margin],
        fill=(52, 152, 219, 255),
        outline=(41, 128, 185, 255),
        width=2 * scale,
    )

    # 冷却アイコン（雪の結晶風）
    center_x, center_y = large_size // 2, large_size // 2

    # 雪の結晶の線
    for angle in [0, 60, 120]:
        import math

        rad = math.radians(angle)
        x1 = center_x + 8 * scale * math.cos(rad)
        y1 = center_y + 8 * scale * math.sin(rad)
        x2 = center_x - 8 * scale * math.cos(rad)
        y2 = center_y - 8 * scale * math.sin(rad)
        draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 255), width=2 * scale)

        # 枝
        for branch_pos in [0.6, -0.6]:
            bx = center_x + branch_pos * 8 * scale * math.cos(rad)
            by = center_y + branch_pos * 8 * scale * math.sin(rad)
            for branch_angle in [30, -30]:
                branch_rad = math.radians(angle + branch_angle)
                bx2 = bx + 3 * scale * math.cos(branch_rad)
                by2 = by + 3 * scale * math.sin(branch_rad)
                draw.line([(bx, by), (bx2, by2)], fill=(255, 255, 255, 255), width=1 * scale)

    # 中心の点
    draw.ellipse(
        [center_x - 2 * scale, center_y - 2 * scale, center_x + 2 * scale, center_y + 2 * scale],
        fill=(255, 255, 255, 255),
    )

    # 32x32に縮小してアンチエイリアス効果を得る
    return img.resize((size, size), Image.Resampling.LANCZOS)


def get_data_period_info(minute_data: list[dict], hourly_data: list[dict]) -> dict:
    """データ期間の情報を取得"""
    all_data = minute_data + hourly_data
    if not all_data:
        return {"start_date": None, "end_date": None, "total_days": 0, "period_text": "データなし"}

    # タイムスタンプを解析
    timestamps = []
    for data in all_data:
        if data.get("timestamp"):
            try:
                timestamps.append(normalize_timestamp(data["timestamp"]))
            except Exception:
                logger.debug("Failed to parse timestamp: %s", data["timestamp"])

    if not timestamps:
        return {
            "start_date": None,
            "end_date": None,
            "total_days": 0,
            "period_text": "タイムスタンプ情報なし",
        }

    start_date = min(timestamps)
    end_date = max(timestamps)
    total_days = (end_date - start_date).days + 1

    # 期間テキストを生成
    start_str = start_date.strftime("%Y年%m月%d日")
    period_text = f"過去{total_days}日間（{start_str}〜）の冷却システム統計"

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_days": total_days,
        "period_text": period_text,
    }


def generate_statistics(minute_data: list[dict], hourly_data: list[dict], error_data: list[dict]) -> dict:
    """メトリクスデータから統計情報を生成"""
    if not minute_data and not hourly_data:
        return {
            "total_days": 0,
            "cooling_mode_avg": None,
            "duty_ratio_avg": None,
            "valve_operations_total": 0,
            "temperature_avg": None,
            "humidity_avg": None,
            "error_total": len(error_data),
            "data_points": 0,
        }

    # 有効なデータのみでフィルタリング
    cooling_modes = [d["cooling_mode"] for d in minute_data if d.get("cooling_mode") is not None]
    duty_ratios = [d["duty_ratio"] for d in minute_data if d.get("duty_ratio") is not None]
    temperatures = [d["temperature"] for d in minute_data if d.get("temperature") is not None]
    humidities = [d["humidity"] for d in minute_data if d.get("humidity") is not None]

    valve_operations_total = sum(d.get("valve_operations", 0) for d in hourly_data)

    # 日数を計算（タイムスタンプから一意の日付を抽出）
    unique_dates = set()
    for d in minute_data + hourly_data:
        if d.get("timestamp"):
            try:
                date_part = (
                    d["timestamp"].split("T")[0]
                    if "T" in str(d["timestamp"])
                    else str(d["timestamp"]).split()[0]
                )
                unique_dates.add(date_part)
            except Exception:
                logger.debug("Failed to parse timestamp for date calculation")

    return {
        "total_days": len(unique_dates),
        "cooling_mode_avg": sum(cooling_modes) / len(cooling_modes) if cooling_modes else None,
        "duty_ratio_avg": sum(duty_ratios) / len(duty_ratios) if duty_ratios else None,
        "valve_operations_total": valve_operations_total,
        "temperature_avg": sum(temperatures) / len(temperatures) if temperatures else None,
        "humidity_avg": sum(humidities) / len(humidities) if humidities else None,
        "error_total": len(error_data),
        "data_points": len(minute_data),
    }


def calculate_correlation(x_values: list, y_values: list) -> float:
    """ピアソンの相関係数を計算"""
    if not x_values or not y_values or len(x_values) != len(y_values):
        return 0.0

    # None値を除外
    valid_pairs = [
        (x, y) for x, y in zip(x_values, y_values, strict=False) if x is not None and y is not None
    ]
    if len(valid_pairs) < 2:
        return 0.0

    x_vals, y_vals = zip(*valid_pairs, strict=False)
    n = len(x_vals)

    # 平均を計算
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n

    # 分子と分母を計算
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals, strict=False))
    x_variance = sum((x - x_mean) ** 2 for x in x_vals)
    y_variance = sum((y - y_mean) ** 2 for y in y_vals)

    denominator = (x_variance * y_variance) ** 0.5

    if denominator == 0:
        return 0.0

    return numerator / denominator


def calculate_boxplot_stats(values: list) -> BoxplotStats:
    """箱ヒゲ図用の統計データを計算"""
    if not values:
        return BoxplotStats(min=0, q1=0, median=0, q3=0, max=0, outliers=[])

    values_sorted = sorted(values)
    n = len(values_sorted)

    # 四分位数を計算
    q1_idx = n // 4
    median_idx = n // 2
    q3_idx = 3 * n // 4

    q1 = values_sorted[q1_idx]
    median = values_sorted[median_idx]
    q3 = values_sorted[q3_idx]

    # IQRと外れ値を計算
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    # 外れ値を特定
    outliers = [v for v in values_sorted if v < lower_bound or v > upper_bound]

    # 外れ値を除いた最小値・最大値
    non_outliers = [v for v in values_sorted if lower_bound <= v <= upper_bound]
    min_val = min(non_outliers) if non_outliers else values_sorted[0]
    max_val = max(non_outliers) if non_outliers else values_sorted[-1]

    return BoxplotStats(min=min_val, q1=q1, median=median, q3=q3, max=max_val, outliers=outliers)


def _extract_hour_from_timestamp(timestamp: str | datetime.datetime) -> int | None:
    """タイムスタンプから時間を抽出"""
    try:
        dt = normalize_timestamp(timestamp)
        return dt.hour
    except Exception:
        logger.debug("Failed to extract hour from timestamp")
        return None


def _prepare_hourly_data(minute_data: list[dict], hourly_data: list[dict]) -> tuple:
    """時間別データを準備"""
    hourly_cooling_mode: list[list] = [[] for _ in range(24)]
    hourly_duty_ratio: list[list] = [[] for _ in range(24)]
    hourly_valve_ops: list[list] = [[] for _ in range(24)]

    # 分データから時間別に集計
    for data in minute_data:
        if data.get("timestamp"):
            hour = _extract_hour_from_timestamp(data["timestamp"])
            if hour is not None and 0 <= hour < 24:
                if data.get("cooling_mode") is not None:
                    hourly_cooling_mode[hour].append(data["cooling_mode"])
                if data.get("duty_ratio") is not None:
                    hourly_duty_ratio[hour].append(data["duty_ratio"])

    # 時間データから時間別バルブ操作数を集計
    for data in hourly_data:
        if data.get("timestamp") and data.get("valve_operations") is not None:
            hour = _extract_hour_from_timestamp(data["timestamp"])
            if hour is not None and 0 <= hour < 24:
                hourly_valve_ops[hour].append(data["valve_operations"])

    return hourly_cooling_mode, hourly_duty_ratio, hourly_valve_ops


def _prepare_timeseries_data(minute_data: list[dict]) -> list[dict]:
    """時系列データを準備（過去100日分）"""
    timeseries_data = []

    # 過去100日分のデータを取得（144000分）
    recent_data = minute_data[-144000:] if len(minute_data) > 144000 else minute_data

    # 時系列表示のため、データを古い順（昇順）に並び替え
    recent_data = list(reversed(recent_data))

    # データポイント数が多い場合は平均化して処理
    target_points = 1000  # 目標ポイント数
    if len(recent_data) > target_points:
        # データを等間隔に分割して平均化
        chunk_size = len(recent_data) // target_points
        averaged_data = []

        for i in range(0, len(recent_data), chunk_size):
            chunk = recent_data[i : i + chunk_size]
            if not chunk:
                continue

            # チャンクの最初のタイムスタンプを使用
            base_data = chunk[0]

            # 数値データの平均を計算
            avg_data = {
                "timestamp": base_data.get("timestamp"),
                "cooling_mode": sum(
                    d.get("cooling_mode") or 0 for d in chunk if d.get("cooling_mode") is not None
                )
                / max(1, sum(1 for d in chunk if d.get("cooling_mode") is not None)),
                "duty_ratio": sum(d.get("duty_ratio") or 0 for d in chunk if d.get("duty_ratio") is not None)
                / max(1, sum(1 for d in chunk if d.get("duty_ratio") is not None)),
                "temperature": sum(
                    d.get("temperature") or 0 for d in chunk if d.get("temperature") is not None
                )
                / max(1, sum(1 for d in chunk if d.get("temperature") is not None)),
                "humidity": sum(d.get("humidity") or 0 for d in chunk if d.get("humidity") is not None)
                / max(1, sum(1 for d in chunk if d.get("humidity") is not None)),
                "lux": sum(d.get("lux") or 0 for d in chunk if d.get("lux") is not None)
                / max(1, sum(1 for d in chunk if d.get("lux") is not None)),
                "solar_radiation": sum(
                    d.get("solar_radiation") or 0 for d in chunk if d.get("solar_radiation") is not None
                )
                / max(1, sum(1 for d in chunk if d.get("solar_radiation") is not None)),
                "rain_amount": sum(
                    d.get("rain_amount") or 0 for d in chunk if d.get("rain_amount") is not None
                )
                / max(1, sum(1 for d in chunk if d.get("rain_amount") is not None)),
            }
            averaged_data.append(avg_data)

        recent_data = averaged_data

    for data in recent_data:
        if data.get("timestamp"):
            # タイムスタンプを簡潔な形式に変換（月/日 時:分）
            try:
                dt = normalize_timestamp(data["timestamp"])
                formatted_timestamp = dt.strftime("%m/%d %H:%M")
            except Exception:
                logger.debug("Failed to parse timestamp for time series formatting")
                formatted_timestamp = str(data["timestamp"])

            timeseries_data.append(
                {
                    "timestamp": formatted_timestamp,
                    "cooling_mode": data.get("cooling_mode"),
                    "duty_ratio": data.get("duty_ratio"),
                    "temperature": data.get("temperature"),
                    "humidity": data.get("humidity"),
                    "lux": data.get("lux"),
                    "solar_radiation": data.get("solar_radiation"),
                    "rain_amount": data.get("rain_amount"),
                }
            )
    return timeseries_data


def _prepare_correlation_data(minute_data: list[dict]) -> dict:
    """環境要因との相関用データを準備"""
    return {
        "cooling_mode": [d.get("cooling_mode") for d in minute_data if d.get("cooling_mode") is not None],
        "duty_ratio": [d.get("duty_ratio") for d in minute_data if d.get("duty_ratio") is not None],
        "temperature": [d.get("temperature") for d in minute_data if d.get("temperature") is not None],
        "humidity": [d.get("humidity") for d in minute_data if d.get("humidity") is not None],
        "lux": [d.get("lux") for d in minute_data if d.get("lux") is not None],
        "solar_radiation": [
            d.get("solar_radiation") for d in minute_data if d.get("solar_radiation") is not None
        ],
        "rain_amount": [d.get("rain_amount") for d in minute_data if d.get("rain_amount") is not None],
    }


def _prepare_boxplot_data(
    hourly_cooling_mode: list, hourly_duty_ratio: list, hourly_valve_ops: list
) -> tuple:
    """箱ヒゲ図用データを生成"""
    boxplot_cooling_mode = []
    boxplot_duty_ratio = []
    boxplot_valve_ops = []

    for hour in range(24):
        boxplot_cooling_mode.append(
            {"x": f"{hour:02d}:00", "y": calculate_boxplot_stats(hourly_cooling_mode[hour]).to_dict()}
        )

        # Duty比をパーセンテージに変換
        duty_ratio_percent = [d * 100 for d in hourly_duty_ratio[hour] if d is not None]
        boxplot_duty_ratio.append(
            {"x": f"{hour:02d}:00", "y": calculate_boxplot_stats(duty_ratio_percent).to_dict()}
        )

        boxplot_valve_ops.append(
            {"x": f"{hour:02d}:00", "y": calculate_boxplot_stats(hourly_valve_ops[hour]).to_dict()}
        )

    return boxplot_cooling_mode, boxplot_duty_ratio, boxplot_valve_ops


def prepare_chart_data(minute_data: list[dict], hourly_data: list[dict]) -> dict:
    """チャート用データを準備"""
    # 各データ準備を個別の関数で処理
    hourly_cooling_mode, hourly_duty_ratio, hourly_valve_ops = _prepare_hourly_data(minute_data, hourly_data)
    timeseries_data = _prepare_timeseries_data(minute_data)
    correlation_data = _prepare_correlation_data(minute_data)
    boxplot_cooling_mode, boxplot_duty_ratio, boxplot_valve_ops = _prepare_boxplot_data(
        hourly_cooling_mode, hourly_duty_ratio, hourly_valve_ops
    )

    return {
        "hourly_cooling_mode": hourly_cooling_mode,
        "hourly_duty_ratio": hourly_duty_ratio,
        "hourly_valve_ops": hourly_valve_ops,
        "boxplot_cooling_mode": boxplot_cooling_mode,
        "boxplot_duty_ratio": boxplot_duty_ratio,
        "boxplot_valve_ops": boxplot_valve_ops,
        "timeseries": timeseries_data,
        "correlation": correlation_data,
    }


def generate_metrics_html(
    stats: dict, minute_data: list[dict], hourly_data: list[dict], period_info: dict
) -> str:
    """Bulma CSSを使用したメトリクスHTMLを生成"""
    # JavaScript用データを準備
    chart_data = prepare_chart_data(minute_data, hourly_data)
    chart_data_json = json.dumps(chart_data)

    favicon_path = f"{unit_cooler.const.URL_PREFIX}/favicon.ico"

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>室外機冷却システム メトリクス ダッシュボード</title>
    <link rel="icon" type="image/x-icon" href="{favicon_path}">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@sgratzl/chartjs-chart-boxplot"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .metrics-card {{ margin-bottom: 1rem; }}
        @media (max-width: 768px) {{
            .metrics-card {{ margin-bottom: 0.75rem; }}
        }}
        .stat-number {{ font-size: 2rem; font-weight: bold; }}
        .chart-container {{ position: relative; height: 350px; margin: 0.5rem 0; }}
        @media (max-width: 768px) {{
            .chart-container {{ height: 300px; margin: 0.25rem 0; }}
            .container.is-fluid {{ padding: 0.25rem !important; }}
            .section {{ padding: 0.5rem 0.25rem !important; }}
            .card {{ margin-bottom: 1rem !important; }}
            .columns {{ margin: 0 !important; }}
            .column {{ padding: 0.25rem !important; }}
        }}
        .japanese-font {{
            font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                         "Noto Sans CJK JP", "Yu Gothic", sans-serif;
        }}
        .permalink-header {{
            position: relative;
            display: inline-block;
        }}
        .permalink-icon {{
            opacity: 0;
            transition: opacity 0.2s ease-in-out;
            cursor: pointer;
            color: #4a90e2;
            margin-left: 0.5rem;
            font-size: 0.8em;
        }}
        .permalink-header:hover .permalink-icon {{
            opacity: 1;
        }}
        .permalink-icon:hover {{
            color: #357abd;
        }}
    </style>
</head>
<body class="japanese-font">
    <div class="container is-fluid" style="padding: 0.5rem;">
        <section class="section" style="padding: 1rem 0.5rem;">
            <div class="container" style="max-width: 100%; padding: 0;">
                <h1 class="title is-2 has-text-centered">
                    <span class="icon is-large"><i class="fas fa-snowflake"></i></span>
                    室外機冷却システム メトリクス ダッシュボード
                </h1>
                <p class="subtitle has-text-centered">{period_info["period_text"]}</p>

                <!-- 基本統計 -->
                {generate_basic_stats_section(stats)}

                <!-- 時間別分布分析 -->
                {generate_hourly_analysis_section()}

                <!-- 時系列データ分析 -->
                {generate_timeseries_section()}

                <!-- 環境要因相関分析 -->
                {generate_correlation_section()}
            </div>
        </section>
    </div>

    <script>
        const chartData = {chart_data_json};

        // チャート生成
        generateHourlyCharts();
        generateTimeseriesCharts();
        generateCorrelationCharts();

        // パーマリンク機能を初期化
        initializePermalinks();

        {generate_chart_javascript()}
    </script>
</html>
    """


def _format_cooling_mode_avg(stats: dict) -> str:
    """冷却モード平均値をフォーマット"""
    return "N/A" if stats["cooling_mode_avg"] is None else f"{stats['cooling_mode_avg']:.2f}"


def _format_duty_ratio_avg(stats: dict) -> str:
    """Duty比平均値をフォーマット"""
    return "N/A" if stats["duty_ratio_avg"] is None else f"{stats['duty_ratio_avg'] * 100:.1f}"


def _format_valve_operations(stats: dict) -> str:
    """バルブ操作回数をフォーマット"""
    return f"{stats['valve_operations_total']:,}"


def generate_basic_stats_section(stats: dict) -> str:
    """基本統計セクションのHTML生成"""
    return f"""
    <div class="section">
        <h2 class="title is-4 permalink-header" id="basic-stats">
            <span class="icon"><i class="fas fa-chart-bar"></i></span>
            基本統計
            <span class="permalink-icon" onclick="copyPermalink('basic-stats')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">システム稼働状況</p>
                    </div>
                    <div class="card-content">
                        <div class="columns is-multiline">
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">❄️ 冷却モード平均</p>
                                    <p class="stat-number has-text-info">{_format_cooling_mode_avg(stats)}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">⚡ Duty比平均</p>
                                    <p class="stat-number has-text-success">
                                        {_format_duty_ratio_avg(stats)}%
                                    </p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">🔧 バルブ操作回数</p>
                                    <p class="stat-number has-text-warning">
                                        {_format_valve_operations(stats)}
                                    </p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">❌ エラー数</p>
                                    <p class="stat-number has-text-danger">{stats["error_total"]:,}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">📊 データポイント数</p>
                                    <p class="stat-number has-text-primary">{stats["data_points"]:,}</p>
                                </div>
                            </div>
                            <div class="column is-one-third">
                                <div class="has-text-centered">
                                    <p class="heading">📅 データ収集日数</p>
                                    <p class="stat-number has-text-primary">{stats["total_days"]:,}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_hourly_analysis_section() -> str:
    """時間別分析セクションのHTML生成"""
    return """
    <div class="section">
        <h2 class="title is-4 permalink-header" id="hourly-analysis">
            <span class="icon"><i class="fas fa-clock"></i></span> 時間別分布分析
            <span class="permalink-icon" onclick="copyPermalink('hourly-analysis')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="cooling-mode-hourly">
                            ❄️ 冷却モードの時間別分布
                            <span class="permalink-icon" onclick="copyPermalink('cooling-mode-hourly')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="coolingModeHourlyChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="duty-ratio-hourly">
                            ⚡ Duty比の時間別分布
                            <span class="permalink-icon" onclick="copyPermalink('duty-ratio-hourly')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="dutyRatioHourlyChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="valve-ops-hourly">
                            🔧 バルブ操作回数の時間別分布
                            <span class="permalink-icon" onclick="copyPermalink('valve-ops-hourly')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="valveOpsHourlyChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_timeseries_section() -> str:
    """時系列データ分析セクションのHTML生成"""
    return """
    <div class="section">
        <h2 class="title is-4 permalink-header" id="timeseries">
            <span class="icon"><i class="fas fa-chart-line"></i></span> 時系列推移分析
            <span class="permalink-icon" onclick="copyPermalink('timeseries')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="cooling-duty-timeseries">
                            📈 冷却モードとDuty比の時系列推移
                            <span class="permalink-icon" onclick="copyPermalink('cooling-duty-timeseries')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="coolingDutyTimeseriesChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="environment-timeseries">
                            🌡️ 環境データの時系列推移
                            <span class="permalink-icon" onclick="copyPermalink('environment-timeseries')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="environmentTimeseriesChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_correlation_section() -> str:
    """環境要因相関分析セクションのHTML生成"""
    return """
    <div class="section">
        <h2 class="title is-4 permalink-header" id="correlation">
            <span class="icon"><i class="fas fa-project-diagram"></i></span> 環境要因相関分析
            <span class="permalink-icon" onclick="copyPermalink('correlation')">
                <i class="fas fa-link"></i>
            </span>
        </h2>

        <div class="columns">
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="temp-cooling-correlation">
                            🌡️❄️ 気温 vs 冷却モード
                            <span class="permalink-icon" onclick="copyPermalink('temp-cooling-correlation')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="tempCoolingCorrelationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="humidity-duty-correlation">
                            💧⚡ 湿度 vs Duty比
                            <span class="permalink-icon" onclick="copyPermalink('humidity-duty-correlation')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="humidityDutyCorrelationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="solar-cooling-correlation">
                            ☀️❄️ 日射量 vs 冷却モード
                            <span class="permalink-icon" onclick="copyPermalink('solar-cooling-correlation')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="solarCoolingCorrelationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title permalink-header" id="lux-duty-correlation">
                            💡⚡ 照度 vs Duty比
                            <span class="permalink-icon" onclick="copyPermalink('lux-duty-correlation')">
                                <i class="fas fa-link"></i>
                            </span>
                        </p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="luxDutyCorrelationChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_chart_javascript() -> str:
    """チャート生成用JavaScriptを生成"""
    return """
        function initializePermalinks() {
            // ページ読み込み時にハッシュがある場合はスクロール
            if (window.location.hash) {
                const element = document.querySelector(window.location.hash);
                if (element) {
                    setTimeout(() => {
                        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }, 500);
                }
            }
        }

        function copyPermalink(sectionId) {
            const url = window.location.origin + window.location.pathname + '#' + sectionId;

            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(url).then(() => {
                    showCopyNotification();
                }).catch(err => {
                    console.error('Failed to copy: ', err);
                    fallbackCopyToClipboard(url);
                });
            } else {
                fallbackCopyToClipboard(url);
            }

            window.history.replaceState(null, null, '#' + sectionId);
        }

        function fallbackCopyToClipboard(text) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                document.execCommand('copy');
                showCopyNotification();
            } catch (err) {
                console.error('Fallback: Failed to copy', err);
                prompt('URLをコピーしてください:', text);
            }

            document.body.removeChild(textArea);
        }

        function showCopyNotification() {
            const notification = document.createElement('div');
            notification.textContent = 'パーマリンクをコピーしました！';
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #23d160;
                color: white;
                padding: 12px 20px;
                border-radius: 4px;
                z-index: 1000;
                font-size: 14px;
                font-weight: 500;
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                transition: opacity 0.3s ease-in-out;
            `;

            document.body.appendChild(notification);

            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => {
                    if (notification.parentNode) {
                        document.body.removeChild(notification);
                    }
                }, 300);
            }, 3000);
        }

        function generateHourlyCharts() {
            // 冷却モードの時間別分布（箱ヒゲ図）
            const coolingModeCtx = document.getElementById('coolingModeHourlyChart');
            if (coolingModeCtx && chartData.boxplot_cooling_mode) {
                new Chart(coolingModeCtx, {
                    type: 'boxplot',
                    data: {
                        labels: chartData.boxplot_cooling_mode.map(d => parseInt(d.x) + '時'),
                        datasets: [{
                            label: '冷却モード分布',
                            data: chartData.boxplot_cooling_mode.map(d => d.y),
                            backgroundColor: 'rgba(52, 152, 219, 0.6)',
                            borderColor: 'rgb(52, 152, 219)',
                            borderWidth: 2,
                            outlierColor: 'rgb(239, 68, 68)',
                            medianColor: 'rgb(255, 193, 7)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: '冷却モード'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '時刻'
                                },
                                ticks: {
                                    maxTicksLimit: 12,
                                    maxRotation: 45
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const stats = context.parsed;
                                        return [
                                            '最小値: ' + stats.min.toFixed(1),
                                            '第1四分位: ' + stats.q1.toFixed(1),
                                            '中央値: ' + stats.median.toFixed(1),
                                            '第3四分位: ' + stats.q3.toFixed(1),
                                            '最大値: ' + stats.max.toFixed(1),
                                            '外れ値数: ' + stats.outliers.length
                                        ];
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // Duty比の時間別分布（箱ヒゲ図）
            const dutyRatioCtx = document.getElementById('dutyRatioHourlyChart');
            if (dutyRatioCtx && chartData.boxplot_duty_ratio) {
                new Chart(dutyRatioCtx, {
                    type: 'boxplot',
                    data: {
                        labels: chartData.boxplot_duty_ratio.map(d => parseInt(d.x) + '時'),
                        datasets: [{
                            label: 'Duty比分布（%）',
                            data: chartData.boxplot_duty_ratio.map(d => d.y),
                            backgroundColor: 'rgba(46, 204, 113, 0.6)',
                            borderColor: 'rgb(46, 204, 113)',
                            borderWidth: 2,
                            outlierColor: 'rgb(239, 68, 68)',
                            medianColor: 'rgb(255, 193, 7)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Duty比（%）'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '時刻'
                                },
                                ticks: {
                                    maxTicksLimit: 12,
                                    maxRotation: 45
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const stats = context.parsed;
                                        return [
                                            '最小値: ' + stats.min.toFixed(1) + '%',
                                            '第1四分位: ' + stats.q1.toFixed(1) + '%',
                                            '中央値: ' + stats.median.toFixed(1) + '%',
                                            '第3四分位: ' + stats.q3.toFixed(1) + '%',
                                            '最大値: ' + stats.max.toFixed(1) + '%',
                                            '外れ値数: ' + stats.outliers.length
                                        ];
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // バルブ操作回数の時間別分布（箱ヒゲ図）
            const valveOpsCtx = document.getElementById('valveOpsHourlyChart');
            if (valveOpsCtx && chartData.boxplot_valve_ops) {
                new Chart(valveOpsCtx, {
                    type: 'boxplot',
                    data: {
                        labels: chartData.boxplot_valve_ops.map(d => parseInt(d.x) + '時'),
                        datasets: [{
                            label: 'バルブ操作回数分布',
                            data: chartData.boxplot_valve_ops.map(d => d.y),
                            backgroundColor: 'rgba(241, 196, 15, 0.6)',
                            borderColor: 'rgb(241, 196, 15)',
                            borderWidth: 2,
                            outlierColor: 'rgb(239, 68, 68)',
                            medianColor: 'rgb(255, 193, 7)'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'バルブ操作回数'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '時刻'
                                },
                                ticks: {
                                    maxTicksLimit: 12,
                                    maxRotation: 45
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const stats = context.parsed;
                                        return [
                                            '最小値: ' + stats.min.toFixed(0) + '回',
                                            '第1四分位: ' + stats.q1.toFixed(0) + '回',
                                            '中央値: ' + stats.median.toFixed(0) + '回',
                                            '第3四分位: ' + stats.q3.toFixed(0) + '回',
                                            '最大値: ' + stats.max.toFixed(0) + '回',
                                            '外れ値数: ' + stats.outliers.length
                                        ];
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }

        function generateTimeseriesCharts() {
            // 冷却モードとDuty比の時系列
            const coolingDutyCtx = document.getElementById('coolingDutyTimeseriesChart');
            if (coolingDutyCtx && chartData.timeseries) {
                const timestamps = chartData.timeseries.map(d => d.timestamp);
                const coolingModes = chartData.timeseries.map(d => d.cooling_mode);
                const dutyRatios = chartData.timeseries.map(d => d.duty_ratio ? d.duty_ratio * 100 : null);

                new Chart(coolingDutyCtx, {
                    type: 'line',
                    data: {
                        labels: timestamps,
                        datasets: [
                            {
                                label: '冷却モード',
                                data: coolingModes,
                                borderColor: 'rgba(52, 152, 219, 1)',
                                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                                tension: 0.1,
                                spanGaps: true,
                                yAxisID: 'y'
                            },
                            {
                                label: 'Duty比（%）',
                                data: dutyRatios,
                                borderColor: 'rgba(46, 204, 113, 1)',
                                backgroundColor: 'rgba(46, 204, 113, 0.1)',
                                tension: 0.1,
                                spanGaps: true,
                                yAxisID: 'y1'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: 'index',
                            intersect: false
                        },
                        scales: {
                            y: {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                title: {
                                    display: true,
                                    text: '冷却モード'
                                }
                            },
                            y1: {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                title: {
                                    display: true,
                                    text: 'Duty比（%）'
                                },
                                grid: {
                                    drawOnChartArea: false,
                                },
                                max: 100,
                                min: 0
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '時刻'
                                },
                                ticks: {
                                    maxTicksLimit: Math.max(6,
                                        Math.min(20, Math.floor(timestamps.length / 10))),
                                    maxRotation: 45,
                                    minRotation: 0,
                                    autoSkip: true,
                                    autoSkipPadding: 20,
                                    callback: function(value, index, values) {
                                        const timestamp = timestamps[index];
                                        if (typeof timestamp === 'string' && timestamp.includes('/')) {
                                            return timestamp;  // 既にフォーマット済み
                                        }
                                        // ISO形式の場合は変換
                                        try {
                                            const date = new Date(timestamp);
                                            const month = (date.getMonth() + 1).toString().padStart(2, '0');
                                            const day = date.getDate().toString().padStart(2, '0');
                                            const hours = date.getHours().toString().padStart(2, '0');
                                            const minutes = date.getMinutes().toString().padStart(2, '0');
                                            return `${month}/${day} ${hours}:${minutes}`;
                                        } catch {
                                            return String(timestamp).substring(0, 16);
                                        }
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // 環境データの時系列
            const environmentCtx = document.getElementById('environmentTimeseriesChart');
            if (environmentCtx && chartData.timeseries) {
                const timestamps = chartData.timeseries.map(d => d.timestamp);
                const temperatures = chartData.timeseries.map(d => d.temperature);
                const solarRadiation = chartData.timeseries.map(d => d.solar_radiation);

                new Chart(environmentCtx, {
                    type: 'line',
                    data: {
                        labels: timestamps,
                        datasets: [
                            {
                                label: '気温（°C）',
                                data: temperatures,
                                borderColor: 'rgba(231, 76, 60, 1)',
                                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                                tension: 0.1,
                                spanGaps: true,
                                yAxisID: 'y'
                            },
                            {
                                label: '日射量（W/m²）',
                                data: solarRadiation,
                                borderColor: 'rgba(255, 193, 7, 1)',
                                backgroundColor: 'rgba(255, 193, 7, 0.1)',
                                tension: 0.1,
                                spanGaps: true,
                                yAxisID: 'y1'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: 'index',
                            intersect: false
                        },
                        scales: {
                            y: {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                title: {
                                    display: true,
                                    text: '気温（°C）'
                                }
                            },
                            y1: {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                title: {
                                    display: true,
                                    text: '日射量（W/m²）'
                                },
                                grid: {
                                    drawOnChartArea: false,
                                },
                                min: 0
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '時刻'
                                },
                                ticks: {
                                    maxTicksLimit: Math.max(6,
                                        Math.min(20, Math.floor(timestamps.length / 10))),
                                    maxRotation: 45,
                                    minRotation: 0,
                                    autoSkip: true,
                                    autoSkipPadding: 20,
                                    callback: function(value, index, values) {
                                        const timestamp = timestamps[index];
                                        if (typeof timestamp === 'string' && timestamp.includes('/')) {
                                            return timestamp;  // 既にフォーマット済み
                                        }
                                        // ISO形式の場合は変換
                                        try {
                                            const date = new Date(timestamp);
                                            const month = (date.getMonth() + 1).toString().padStart(2, '0');
                                            const day = date.getDate().toString().padStart(2, '0');
                                            const hours = date.getHours().toString().padStart(2, '0');
                                            const minutes = date.getMinutes().toString().padStart(2, '0');
                                            return `${month}/${day} ${hours}:${minutes}`;
                                        } catch {
                                            return String(timestamp).substring(0, 16);
                                        }
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }

        function generateCorrelationCharts() {
            // 相関係数計算用のヘルパー関数
            function calculateCorrelation(xVals, yVals) {
                const validPairs = [];
                for (let i = 0; i < Math.min(xVals.length, yVals.length); i++) {
                    if (xVals[i] !== null && yVals[i] !== null) {
                        validPairs.push([xVals[i], yVals[i]]);
                    }
                }

                if (validPairs.length < 2) return 0;

                const xMean = validPairs.reduce((sum, pair) => sum + pair[0], 0) / validPairs.length;
                const yMean = validPairs.reduce((sum, pair) => sum + pair[1], 0) / validPairs.length;

                let numerator = 0;
                let xVariance = 0;
                let yVariance = 0;

                for (const [x, y] of validPairs) {
                    numerator += (x - xMean) * (y - yMean);
                    xVariance += Math.pow(x - xMean, 2);
                    yVariance += Math.pow(y - yMean, 2);
                }

                const denominator = Math.sqrt(xVariance * yVariance);
                return denominator === 0 ? 0 : numerator / denominator;
            }

            // 気温 vs 冷却モード
            const tempCoolingCtx = document.getElementById('tempCoolingCorrelationChart');
            if (tempCoolingCtx && chartData.correlation) {
                const data = [];
                const minLength = Math.min(
                    chartData.correlation.temperature.length,
                    chartData.correlation.cooling_mode.length
                );
                for (let i = 0; i < minLength; i++) {
                    if (chartData.correlation.temperature[i] !== null &&
                        chartData.correlation.cooling_mode[i] !== null) {
                        data.push({
                            x: chartData.correlation.temperature[i],
                            y: chartData.correlation.cooling_mode[i]
                        });
                    }
                }

                const correlation = calculateCorrelation(
                    chartData.correlation.temperature,
                    chartData.correlation.cooling_mode
                );

                new Chart(tempCoolingCtx, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: `気温 vs 冷却モード (r=${correlation.toFixed(3)})`,
                            data: data,
                            backgroundColor: 'rgba(231, 76, 60, 0.6)',
                            borderColor: 'rgba(231, 76, 60, 1)',
                            pointRadius: 3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: '気温（°C）'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: '冷却モード'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    title: function(context) {
                                        return `データポイント: ${context.length}個`;
                                    },
                                    label: function(context) {
                                        return [
                                            `気温: ${context.parsed.x.toFixed(1)}°C`,
                                            `冷却モード: ${context.parsed.y.toFixed(1)}`,
                                            `相関係数: ${correlation.toFixed(3)}`
                                        ];
                                    },
                                    afterLabel: function() {
                                        const strength = Math.abs(correlation);
                                        if (strength >= 0.8) return '強い相関';
                                        if (strength >= 0.5) return '中程度の相関';
                                        if (strength >= 0.3) return '弱い相関';
                                        return '相関なし';
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // 湿度 vs Duty比
            const humidityDutyCtx = document.getElementById('humidityDutyCorrelationChart');
            if (humidityDutyCtx && chartData.correlation) {
                const data = [];
                const minLength = Math.min(
                    chartData.correlation.humidity.length,
                    chartData.correlation.duty_ratio.length
                );
                for (let i = 0; i < minLength; i++) {
                    if (
                        chartData.correlation.humidity[i] !== null &&
                        chartData.correlation.duty_ratio[i] !== null
                    ) {
                        data.push({
                            x: chartData.correlation.humidity[i],
                            y: chartData.correlation.duty_ratio[i] * 100
                        });
                    }
                }

                const correlation = calculateCorrelation(
                    chartData.correlation.humidity,
                    chartData.correlation.duty_ratio
                );

                new Chart(humidityDutyCtx, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: `湿度 vs Duty比 (r=${correlation.toFixed(3)})`,
                            data: data,
                            backgroundColor: 'rgba(155, 89, 182, 0.6)',
                            borderColor: 'rgba(155, 89, 182, 1)',
                            pointRadius: 3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: '湿度（%）'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Duty比（%）'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    title: function(context) {
                                        return `データポイント: ${context.length}個`;
                                    },
                                    label: function(context) {
                                        return [
                                            `湿度: ${context.parsed.x.toFixed(1)}%`,
                                            `Duty比: ${context.parsed.y.toFixed(1)}%`,
                                            `相関係数: ${correlation.toFixed(3)}`
                                        ];
                                    },
                                    afterLabel: function() {
                                        const strength = Math.abs(correlation);
                                        if (strength >= 0.8) return '強い相関';
                                        if (strength >= 0.5) return '中程度の相関';
                                        if (strength >= 0.3) return '弱い相関';
                                        return '相関なし';
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // 日射量 vs 冷却モード
            const solarCoolingCtx = document.getElementById('solarCoolingCorrelationChart');
            if (solarCoolingCtx && chartData.correlation) {
                const data = [];
                const minLength = Math.min(
                    chartData.correlation.solar_radiation.length,
                    chartData.correlation.cooling_mode.length
                );
                for (let i = 0; i < minLength; i++) {
                    if (
                        chartData.correlation.solar_radiation[i] !== null &&
                        chartData.correlation.cooling_mode[i] !== null
                    ) {
                        data.push({
                            x: chartData.correlation.solar_radiation[i],
                            y: chartData.correlation.cooling_mode[i]
                        });
                    }
                }

                const solarCorrelation = calculateCorrelation(
                    chartData.correlation.solar_radiation,
                    chartData.correlation.cooling_mode
                );

                new Chart(solarCoolingCtx, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: `日射量 vs 冷却モード (r=${solarCorrelation.toFixed(3)})`,
                            data: data,
                            backgroundColor: 'rgba(243, 156, 18, 0.6)',
                            borderColor: 'rgba(243, 156, 18, 1)',
                            pointRadius: 3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: '日射量（W/m²）'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: '冷却モード'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    title: function(context) {
                                        return `データポイント: ${context.length}個`;
                                    },
                                    label: function(context) {
                                        return [
                                            `日射量: ${context.parsed.x.toFixed(1)} W/m²`,
                                            `冷却モード: ${context.parsed.y.toFixed(1)}`,
                                            `相関係数: ${solarCorrelation.toFixed(3)}`
                                        ];
                                    },
                                    afterLabel: function() {
                                        const strength = Math.abs(solarCorrelation);
                                        if (strength >= 0.8) return '強い相関';
                                        if (strength >= 0.5) return '中程度の相関';
                                        if (strength >= 0.3) return '弱い相関';
                                        return '相関なし';
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // 照度 vs Duty比
            const luxDutyCtx = document.getElementById('luxDutyCorrelationChart');
            if (luxDutyCtx && chartData.correlation) {
                const data = [];
                const minLength = Math.min(
                    chartData.correlation.lux.length,
                    chartData.correlation.duty_ratio.length
                );
                for (let i = 0; i < minLength; i++) {
                    if (
                        chartData.correlation.lux[i] !== null &&
                        chartData.correlation.duty_ratio[i] !== null
                    ) {
                        data.push({
                            x: chartData.correlation.lux[i],
                            y: chartData.correlation.duty_ratio[i] * 100
                        });
                    }
                }

                const luxCorrelation = calculateCorrelation(
                    chartData.correlation.lux,
                    chartData.correlation.duty_ratio
                );

                new Chart(luxDutyCtx, {
                    type: 'scatter',
                    data: {
                        datasets: [{
                            label: `照度 vs Duty比 (r=${luxCorrelation.toFixed(3)})`,
                            data: data,
                            backgroundColor: 'rgba(52, 152, 219, 0.6)',
                            borderColor: 'rgba(52, 152, 219, 1)',
                            pointRadius: 3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: '照度（lux）'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Duty比（%）'
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    title: function(context) {
                                        return `データポイント: ${context.length}個`;
                                    },
                                    label: function(context) {
                                        return [
                                            `照度: ${context.parsed.x.toFixed(1)} lux`,
                                            `Duty比: ${context.parsed.y.toFixed(1)}%`,
                                            `相関係数: ${luxCorrelation.toFixed(3)}`
                                        ];
                                    },
                                    afterLabel: function() {
                                        const strength = Math.abs(luxCorrelation);
                                        if (strength >= 0.8) return '強い相関';
                                        if (strength >= 0.5) return '中程度の相関';
                                        if (strength >= 0.3) return '弱い相関';
                                        return '相関なし';
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }
    """
