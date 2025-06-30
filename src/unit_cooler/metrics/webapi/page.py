import io
import json
import logging
import pathlib

import flask
import my_lib.config
import my_lib.flask_util
import my_lib.webapp.config
from PIL import Image, ImageDraw

import unit_cooler.metrics.collector

from . import page_js

blueprint = flask.Blueprint("metrics_dashboard", __name__, url_prefix=my_lib.webapp.config.URL_PREFIX)


@blueprint.route("/api/metrics", methods=["GET"])
@my_lib.flask_util.gzipped
def metrics_view():
    # NOTE: @gzipped をつけた場合、キャッシュ用のヘッダを付与しているので、
    # 無効化する。
    flask.g.disable_cache = True

    try:
        # 設定ファイルからデータベースパスを取得
        config_file = flask.current_app.config.get("CONFIG_FILE_NORMAL", "config.yaml")
        config = my_lib.config.load(config_file, pathlib.Path("config.schema"))

        # 設定からデータベースパスを取得
        db_path = config.get("metrics", {}).get("data", "data/metrics.db")

        # メトリクス分析器を初期化
        analyzer = unit_cooler.metrics.collector.MetricsAnalyzer(db_path)

        # すべてのメトリクスデータを収集
        basic_stats = analyzer.get_basic_statistics(days=30)
        hourly_patterns = analyzer.get_hourly_patterns(days=30)
        anomalies = analyzer.detect_anomalies(days=30)
        correlation_analysis = analyzer.get_correlation_analysis(days=30)
        alerts = analyzer.check_performance_alerts()

        # HTMLを生成
        html_content = generate_metrics_html(
            basic_stats, hourly_patterns, anomalies, correlation_analysis, alerts
        )

        return flask.Response(html_content, mimetype="text/html")

    except Exception as e:
        logging.exception("メトリクス表示の生成エラー")
        return flask.Response(f"エラー: {e!s}", mimetype="text/plain", status=500)


def generate_metrics_icon():
    """室外機冷却システム用のアイコンを動的生成（アンチエイリアス対応）"""
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

    # 室外機っぽい四角形
    unit_margin = 8 * scale
    draw.rectangle(
        [
            unit_margin,
            unit_margin + 4 * scale,
            large_size - unit_margin,
            large_size - unit_margin - 2 * scale,
        ],
        fill=(255, 255, 255, 255),
        outline=(41, 128, 185, 255),
        width=1 * scale,
    )

    # 冷却ファンの円
    fan_center_x = large_size // 2
    fan_center_y = large_size // 2 + 2 * scale
    fan_radius = 6 * scale
    draw.ellipse(
        [
            fan_center_x - fan_radius,
            fan_center_y - fan_radius,
            fan_center_x + fan_radius,
            fan_center_y + fan_radius,
        ],
        outline=(41, 128, 185, 255),
        width=2 * scale,
    )

    # ファンの羽根
    for i in range(4):
        angle_start = i * 90
        angle_end = angle_start + 30
        draw.arc(
            [
                fan_center_x - fan_radius // 2,
                fan_center_y - fan_radius // 2,
                fan_center_x + fan_radius // 2,
                fan_center_y + fan_radius // 2,
            ],
            start=angle_start,
            end=angle_end,
            fill=(41, 128, 185, 255),
            width=1 * scale,
        )

    # 水滴（ミスト）
    for _i, (x_offset, y_offset) in enumerate([(6, -8), (-6, -8), (0, -12)]):
        drop_x = fan_center_x + x_offset * scale
        drop_y = fan_center_y + y_offset * scale
        drop_size = 2 * scale
        draw.ellipse(
            [drop_x - drop_size, drop_y - drop_size, drop_x + drop_size, drop_y + drop_size],
            fill=(100, 200, 255, 200),
        )

    # 32x32に縮小してアンチエイリアス効果を得る
    return img.resize((size, size), Image.LANCZOS)


@blueprint.route("/favicon.ico", methods=["GET"])
def favicon():
    """動的生成された室外機冷却システム用favicon.icoを返す"""
    try:
        # メトリクスアイコンを生成
        img = generate_metrics_icon()

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
        logging.exception("favicon生成エラー")
        return flask.Response("", status=500)


def generate_metrics_html(basic_stats, hourly_patterns, anomalies, correlation_analysis, alerts):
    """Bulma CSSを使用した包括的な室外機冷却システムメトリクスHTMLを生成。"""
    # JavaScript チャート用にデータをJSONに変換
    hourly_data_json = json.dumps(hourly_patterns)
    anomalies_data_json = json.dumps(anomalies)
    correlation_data_json = json.dumps(correlation_analysis)

    # URL_PREFIXを取得してfaviconパスを構築
    favicon_path = f"{my_lib.webapp.config.URL_PREFIX}/favicon.ico"

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
        .metrics-card {{ margin-bottom: 1.5rem; }}
        .stat-number {{ font-size: 2rem; font-weight: bold; }}
        .chart-container {{ position: relative; height: 450px; margin: 1rem 0; }}
        .chart-legend {{ margin-bottom: 1rem; }}
        .legend-item {{ display: inline-block; margin-right: 1rem; margin-bottom: 0.5rem; }}
        .legend-color {{
            display: inline-block; width: 20px; height: 3px;
            margin-right: 0.5rem; vertical-align: middle;
        }}
        .legend-dashed {{ border-top: 3px dashed; height: 0; }}
        .legend-dotted {{ border-top: 3px dotted; height: 0; }}
        .anomaly-item {{
            margin-bottom: 1rem;
            padding: 0.75rem;
            background-color: #fafafa;
            border-radius: 6px;
            border-left: 4px solid #ffdd57;
        }}
        .alert-item {{ margin-bottom: 1rem; }}
        .correlation-item {{
            padding: 0.75rem;
            background-color: #f8f9fa;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            border-left: 4px solid;
        }}
        .correlation-strong {{ border-left-color: #e74c3c; }}
        .correlation-moderate {{ border-left-color: #f39c12; }}
        .correlation-weak {{ border-left-color: #95a5a6; }}
        .japanese-font {{
            font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                         "Noto Sans CJK JP", "Yu Gothic", sans-serif;
        }}
    </style>
</head>
<body class="japanese-font">
    <div class="container is-fluid">
        <section class="section">
            <div class="container">
                <h1 class="title is-2 has-text-centered">
                    <span class="icon is-large"><i class="fas fa-wind"></i></span>
                    室外機冷却システム メトリクス ダッシュボード
                </h1>
                <p class="subtitle has-text-centered">過去30日間のシステムパフォーマンス監視と分析</p>

                <!-- アラート -->
                {generate_alerts_section(alerts)}

                <!-- 基本統計 -->
                {generate_basic_stats_section(basic_stats)}

                <!-- 時間別パターン -->
                {generate_hourly_patterns_section(hourly_patterns)}

                <!-- 相関分析 -->
                {generate_correlation_analysis_section(correlation_analysis)}

                <!-- 異常検知 -->
                {generate_anomalies_section(anomalies)}
            </div>
        </section>
    </div>

    <script>
        const hourlyData = {hourly_data_json};
        const anomaliesData = {anomalies_data_json};
        const correlationData = {correlation_data_json};

        // チャート生成
        generateHourlyCharts();
        generateBoxplotCharts();
        generateCorrelationCharts();

        {page_js.generate_chart_javascript()}
    </script>
</html>
    """


def generate_alerts_section(alerts):
    """アラートセクションのHTML生成。"""
    if not alerts:
        return """
        <div class="notification is-success">
            <span class="icon"><i class="fas fa-check-circle"></i></span>
            システムアラートは検出されていません。
        </div>
        """

    alerts_html = (
        '<div class="section"><h2 class="title is-4">'
        '<span class="icon"><i class="fas fa-exclamation-triangle"></i></span> '
        "システムアラート</h2>"
    )

    for alert in alerts:
        severity_class = {"critical": "is-danger", "warning": "is-warning", "info": "is-info"}.get(
            alert.get("severity", "info"), "is-info"
        )

        alert_type = alert.get("type", "アラート").replace("_", " ")
        alert_message = alert.get("message", "メッセージなし")

        alerts_html += f"""
        <div class="notification {severity_class} alert-item">
            <strong>{alert_type}:</strong> {alert_message}
        </div>
        """

    alerts_html += "</div>"
    return alerts_html


def generate_basic_stats_section(basic_stats):
    """基本統計セクションのHTML生成。"""
    system_metrics = basic_stats.get("system_metrics", {})

    return f"""
    <div class="section">
        <h2 class="title is-4">
            <span class="icon"><i class="fas fa-chart-bar"></i></span>
            基本統計（過去30日間）
        </h2>

        <div class="columns is-multiline">
            <div class="column is-one-quarter">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">バルブ操作</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">総操作回数</p>
                        <p class="stat-number has-text-primary">
                            {system_metrics.get("total_valve_operations", 0):,}
                        </p>
                    </div>
                </div>
            </div>

            <div class="column is-one-quarter">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">センサー読み取り</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">総読み取り回数</p>
                        <p class="stat-number has-text-info">
                            {system_metrics.get("total_sensor_reads", 0):,}
                        </p>
                    </div>
                </div>
            </div>

            <div class="column is-one-quarter">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">平均デューティサイクル</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">稼働率</p>
                        <p class="stat-number has-text-success">
                            {system_metrics.get("avg_duty_cycle", 0):.1f}%
                        </p>
                    </div>
                </div>
            </div>

            <div class="column is-one-quarter">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">エラー</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">総エラー数</p>
                        <p class="stat-number has-text-danger">
                            {system_metrics.get("total_errors", 0):,}
                        </p>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column is-one-third">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">平均温度</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">環境温度</p>
                        <p class="stat-number has-text-warning">
                            {system_metrics.get("avg_temperature", 0):.1f}°C
                        </p>
                    </div>
                </div>
            </div>

            <div class="column is-one-third">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">平均日射量</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">太陽放射</p>
                        <p class="stat-number has-text-link">
                            {system_metrics.get("avg_solar_radiation", 0):.0f} W/m²
                        </p>
                    </div>
                </div>
            </div>

            <div class="column is-one-third">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">平均流量</p>
                    </div>
                    <div class="card-content has-text-centered">
                        <p class="heading">ミスト流量</p>
                        <p class="stat-number has-text-cyan">
                            {system_metrics.get("avg_flow_value", 0):.2f} L/min
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_hourly_patterns_section(hourly_patterns):  # noqa: ARG001
    """時間別パターンセクションのHTML生成。"""
    return """
    <div class="section">
        <h2 class="title is-4">
            <span class="icon"><i class="fas fa-clock"></i></span>
            時間別システムパフォーマンス
        </h2>

        <div class="columns">
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">デューティサイクル - 時間別パフォーマンス</p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="dutyCycleHourlyChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">環境要因 - 時間別パフォーマンス</p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="environmentalHourlyChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="columns">
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">デューティサイクル - 時間別分布（箱ひげ図）</p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="dutyCycleBoxplotChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">温度 - 時間別分布（箱ひげ図）</p>
                    </div>
                    <div class="card-content">
                        <div class="chart-container">
                            <canvas id="temperatureBoxplotChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """


def generate_correlation_analysis_section(correlation_analysis):
    """相関分析セクションのHTML生成。"""
    if "error" in correlation_analysis:
        return f"""
        <div class="section">
            <h2 class="title is-4">
                <span class="icon"><i class="fas fa-project-diagram"></i></span>
                相関分析
            </h2>
            <div class="notification is-warning">
                <span class="icon"><i class="fas fa-exclamation-triangle"></i></span>
                相関分析が利用できません: {correlation_analysis["error"]}
            </div>
        </div>
        """

    correlations = correlation_analysis.get("correlations", {})
    ranking = correlation_analysis.get("ranking", {})

    correlation_html = """
    <div class="section">
        <h2 class="title is-4">
            <span class="icon"><i class="fas fa-project-diagram"></i></span>
            環境要因とシステム稼働率の相関分析
        </h2>

        <div class="notification is-info is-light">
            <p><strong>相関分析について：</strong></p>
            <p>環境要因（温度、湿度、日射量、電力消費、雨量、流量）とバルブのデューティサイクル（稼働率）との相関を分析しています。</p>
            <ul>
                <li><strong>強い相関 (|r| > 0.7)</strong>：要因が稼働率に大きく影響</li>
                <li><strong>中程度の相関 (0.3 < |r| ≤ 0.7)</strong>：要因が稼働率にある程度影響</li>
                <li><strong>弱い相関 (|r| ≤ 0.3)</strong>：要因が稼働率にわずかに影響</li>
            </ul>
        </div>

        <div class="columns">
    """

    # 有意な相関がある場合のランキング
    if ranking.get("most_influential_factors"):
        correlation_html += """
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">影響度ランキング</p>
                    </div>
                    <div class="card-content">
        """

        for i, factor in enumerate(ranking["most_influential_factors"], 1):
            strength_class = {
                "strong": "correlation-strong",
                "moderate": "correlation-moderate",
                "weak": "correlation-weak",
            }.get(factor["strength"], "correlation-weak")

            direction_icon = "⬆️" if factor["direction"] == "positive" else "⬇️"

            correlation_html += f"""
                        <div class="correlation-item {strength_class}">
                            <div class="level is-mobile">
                                <div class="level-left">
                                    <div class="level-item">
                                        <strong>#{i} {factor["name"]}</strong>
                                    </div>
                                </div>
                                <div class="level-right">
                                    <div class="level-item">
                                        <span class="tag is-small">
                                            {direction_icon} {factor["correlation_coefficient"]:.3f}
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <p class="is-size-7">
                                {factor["strength"].title()} correlation ({factor["direction"]})
                            </p>
                        </div>
            """

        correlation_html += """
                    </div>
                </div>
            </div>
        """

    # 詳細な相関情報
    correlation_html += """
            <div class="column is-half">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">詳細分析</p>
                    </div>
                    <div class="card-content">
    """

    total_analyzed = ranking.get("total_analyzed", 0)
    total_significant = ranking.get("total_significant", 0)

    correlation_html += f"""
                        <div class="columns is-mobile">
                            <div class="column has-text-centered">
                                <p class="heading">分析要因数</p>
                                <p class="title is-4">{total_analyzed}</p>
                            </div>
                            <div class="column has-text-centered">
                                <p class="heading">有意な相関</p>
                                <p class="title is-4 has-text-success">{total_significant}</p>
                            </div>
                        </div>
    """

    if correlations:
        correlation_html += '<div class="content"><h6>全要因の詳細:</h6>'
        for factor_data in correlations.values():
            significance_color = (
                "has-text-success" if factor_data["significance"] == "significant" else "has-text-grey"
            )
            correlation_html += f"""
                        <p class="{significance_color}">
                            <strong>{factor_data["name"]}</strong>:
                            r = {factor_data["correlation_coefficient"]:.3f}
                            ({factor_data["strength"]}, {factor_data["direction"]})
                            - {factor_data["data_points"]}件
                        </p>
            """
        correlation_html += "</div>"

    correlation_html += """
                    </div>
                </div>
            </div>
        </div>
    </div>
    """

    return correlation_html


def generate_anomalies_section(anomalies):  # noqa: C901, PLR0912, PLR0915
    """異常検知セクションのHTML生成。"""
    if "error" in anomalies:
        return f"""
        <div class="section">
            <h2 class="title is-4">
                <span class="icon"><i class="fas fa-search"></i></span>
                異常検知
            </h2>
            <div class="notification is-warning">
                <span class="icon"><i class="fas fa-exclamation-triangle"></i></span>
                異常検知が利用できません: {anomalies["error"]}
            </div>
        </div>
        """

    anomaly_count = anomalies.get("anomalies_detected", 0)
    total_samples = anomalies.get("total_samples", 0)
    anomaly_rate = anomalies.get("anomaly_rate", 0) * 100

    anomalies_html = f"""
    <div class="section">
        <h2 class="title is-4">
            <span class="icon"><i class="fas fa-search"></i></span>
            異常検知
        </h2>

        <div class="notification is-info is-light">
            <p><strong>異常検知について：</strong></p>
            <p>
                機械学習の<strong>Isolation Forest</strong>アルゴリズムを使用して、
                以下の要素から異常なパターンを検知しています：
            </p>
            <ul>
                <li><strong>デューティサイクル</strong>：通常と異なる稼働パターン</li>
                <li><strong>環境要因</strong>：温度、日射量、流量の異常値</li>
                <li><strong>時間パターン</strong>：通常の時間パターンと異なる動作</li>
                <li><strong>エラー発生</strong>：システムエラーの有無</li>
            </ul>
        </div>

        <div class="columns">
            <div class="column">
                <div class="card metrics-card">
                    <div class="card-header">
                        <p class="card-header-title">異常検知結果</p>
                    </div>
                    <div class="card-content">
                        <div class="columns">
                            <div class="column has-text-centered">
                                <p class="heading">総サンプル数</p>
                                <p class="stat-number has-text-info">{total_samples}</p>
                            </div>
                            <div class="column has-text-centered">
                                <p class="heading">検出された異常数</p>
                                <p class="stat-number has-text-warning">{anomaly_count}</p>
                            </div>
                            <div class="column has-text-centered">
                                <p class="heading">異常率</p>
                                <p class="stat-number has-text-warning">{anomaly_rate:.2f}%</p>
                            </div>
                        </div>
    """

    # 個別の異常がある場合は表示
    if anomalies.get("anomalies"):
        anomalies_html += '<div class="content"><h5>最近の異常:</h5>'
        # 新しいもの順でソート
        sorted_anomalies = sorted(anomalies["anomalies"], key=lambda x: x.get("timestamp", ""), reverse=True)
        for anomaly in sorted_anomalies[:10]:  # 最新10件を表示
            timestamp_str = anomaly.get("timestamp", "不明")
            duty_cycle = anomaly.get("duty_cycle", 0)
            temperature = anomaly.get("temperature")
            solar_radiation = anomaly.get("solar_radiation")
            flow_value = anomaly.get("flow_value")
            errors = anomaly.get("errors", 0)

            # 異常の詳細を分析
            anomaly_details = []
            anomaly_reasons = []

            if duty_cycle > 80:
                anomaly_reasons.append('<span class="tag is-small is-warning">高稼働率</span>')
                anomaly_details.append(f"デューティサイクル: <strong>{duty_cycle:.1f}%</strong>")
            elif duty_cycle < 5:
                anomaly_reasons.append('<span class="tag is-small is-info">低稼働率</span>')
                anomaly_details.append(f"デューティサイクル: <strong>{duty_cycle:.1f}%</strong>")

            if temperature and temperature > 35:
                anomaly_reasons.append('<span class="tag is-small is-danger">高温</span>')
                anomaly_details.append(f"温度: <strong>{temperature:.1f}°C</strong>")

            if solar_radiation and solar_radiation > 800:
                anomaly_reasons.append('<span class="tag is-small is-warning">強日射</span>')
                anomaly_details.append(f"日射量: <strong>{solar_radiation:.0f} W/m²</strong>")

            if flow_value and flow_value > 5:
                anomaly_reasons.append('<span class="tag is-small is-success">高流量</span>')
                anomaly_details.append(f"流量: <strong>{flow_value:.2f} L/min</strong>")

            if errors > 0:
                anomaly_reasons.append('<span class="tag is-small is-danger">エラー発生</span>')
                anomaly_details.append(f"エラー数: <strong>{errors}</strong>")

            if not anomaly_reasons:
                anomaly_reasons.append('<span class="tag is-small is-light">パターン異常</span>')

            # 日時をフォーマット
            try:
                import datetime

                if timestamp_str != "不明":
                    dt = datetime.datetime.fromisoformat(timestamp_str.replace("+09:00", "+09:00"))
                    formatted_time = dt.strftime("%m月%d日 %H時%M分")
                else:
                    formatted_time = "不明"
            except Exception:
                formatted_time = timestamp_str

            reason_tags = " ".join(anomaly_reasons)
            detail_text = " | ".join(anomaly_details)
            anomalies_html += f"""<div class="anomaly-item">
                <div class="mb-2">
                    <span class="tag is-warning">{formatted_time}</span>
                    {reason_tags}
                </div>
                <div class="pl-3 has-text-grey-dark" style="font-size: 0.9rem;">
                    {detail_text}
                </div>
            </div>"""
        anomalies_html += "</div>"

    anomalies_html += """
                    </div>
                </div>
            </div>
        </div>
    </div>
    """

    return anomalies_html
