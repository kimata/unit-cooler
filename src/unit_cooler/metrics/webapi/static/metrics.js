/**
 * メトリクスダッシュボードのチャート描画
 *
 * body の data-api-url で指定されたエンドポイントから JSON を取得し、
 * Chart.js で各チャートを描画する。
 */
"use strict";

// 箱ヒゲ図チャートの設定
const BOXPLOT_CHARTS = [
    {
        canvasId: "coolingModeHourlyChart",
        key: "boxplot_cooling_mode",
        label: "冷却モード分布",
        axisLabel: "冷却モード",
        color: "52, 152, 219",
        unit: "",
        digits: 1,
    },
    {
        canvasId: "dutyRatioHourlyChart",
        key: "boxplot_duty_ratio",
        label: "Duty比分布（%）",
        axisLabel: "Duty比（%）",
        color: "46, 204, 113",
        unit: "%",
        digits: 1,
    },
    {
        canvasId: "valveOpsHourlyChart",
        key: "boxplot_valve_ops",
        label: "バルブ操作回数分布",
        axisLabel: "バルブ操作回数",
        color: "241, 196, 15",
        unit: "回",
        digits: 0,
    },
];

// 時系列チャートの設定
const TIMESERIES_CHARTS = [
    {
        canvasId: "coolingDutyTimeseriesChart",
        datasets: [
            { label: "冷却モード", column: "cooling_mode", color: "52, 152, 219", scale: 1, axis: "y" },
            { label: "Duty比（%）", column: "duty_ratio", color: "46, 204, 113", scale: 100, axis: "y1" },
        ],
        leftAxis: { title: "冷却モード" },
        rightAxis: { title: "Duty比（%）", min: 0, max: 100 },
    },
    {
        canvasId: "environmentTimeseriesChart",
        datasets: [
            { label: "気温（°C）", column: "temperature", color: "231, 76, 60", scale: 1, axis: "y" },
            {
                label: "日射量（W/m²）",
                column: "solar_radiation",
                color: "255, 193, 7",
                scale: 1,
                axis: "y1",
            },
        ],
        leftAxis: { title: "気温（°C）" },
        rightAxis: { title: "日射量（W/m²）", min: 0 },
    },
];

// 散布図チャートの設定
const SCATTER_CHARTS = [
    {
        canvasId: "tempCoolingCorrelationChart",
        key: "temp_cooling",
        name: "気温 vs 冷却モード",
        xName: "気温",
        xLabel: "気温（°C）",
        xUnit: "°C",
        yName: "冷却モード",
        yLabel: "冷却モード",
        yUnit: "",
        yScale: 1,
        color: "231, 76, 60",
    },
    {
        canvasId: "humidityDutyCorrelationChart",
        key: "humidity_duty",
        name: "湿度 vs Duty比",
        xName: "湿度",
        xLabel: "湿度（%）",
        xUnit: "%",
        yName: "Duty比",
        yLabel: "Duty比（%）",
        yUnit: "%",
        yScale: 100,
        color: "155, 89, 182",
    },
    {
        canvasId: "solarCoolingCorrelationChart",
        key: "solar_cooling",
        name: "日射量 vs 冷却モード",
        xName: "日射量",
        xLabel: "日射量（W/m²）",
        xUnit: " W/m²",
        yName: "冷却モード",
        yLabel: "冷却モード",
        yUnit: "",
        yScale: 1,
        color: "243, 156, 18",
    },
    {
        canvasId: "luxDutyCorrelationChart",
        key: "lux_duty",
        name: "照度 vs Duty比",
        xName: "照度",
        xLabel: "照度（lux）",
        xUnit: " lux",
        yName: "Duty比",
        yLabel: "Duty比（%）",
        yUnit: "%",
        yScale: 100,
        color: "52, 152, 219",
    },
];

// ピアソン相関係数を計算する（x, y はペア済み配列）
function calculateCorrelation(xs, ys) {
    const n = Math.min(xs.length, ys.length);
    if (n < 2) {
        return 0;
    }

    const xMean = xs.reduce((sum, v) => sum + v, 0) / n;
    const yMean = ys.reduce((sum, v) => sum + v, 0) / n;

    let numerator = 0;
    let xVariance = 0;
    let yVariance = 0;

    for (let i = 0; i < n; i++) {
        numerator += (xs[i] - xMean) * (ys[i] - yMean);
        xVariance += Math.pow(xs[i] - xMean, 2);
        yVariance += Math.pow(ys[i] - yMean, 2);
    }

    const denominator = Math.sqrt(xVariance * yVariance);
    return denominator === 0 ? 0 : numerator / denominator;
}

function correlationStrengthLabel(r) {
    const strength = Math.abs(r);
    if (strength >= 0.8) return "強い相関";
    if (strength >= 0.5) return "中程度の相関";
    if (strength >= 0.3) return "弱い相関";
    return "相関なし";
}

function makeTimestampTickFormatter(timestamps) {
    return function (value, index) {
        const timestamp = timestamps[index];
        if (typeof timestamp === "string" && timestamp.includes("/")) {
            return timestamp; // 既にフォーマット済み
        }
        // ISO形式の場合は変換
        try {
            const date = new Date(timestamp);
            const month = String(date.getMonth() + 1).padStart(2, "0");
            const day = String(date.getDate()).padStart(2, "0");
            const hours = String(date.getHours()).padStart(2, "0");
            const minutes = String(date.getMinutes()).padStart(2, "0");
            return `${month}/${day} ${hours}:${minutes}`;
        } catch {
            return String(timestamp).substring(0, 16);
        }
    };
}

function makeBoxplotChart(canvasId, data, opts) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !data) {
        return;
    }

    new Chart(ctx, {
        type: "boxplot",
        data: {
            labels: data.map((d) => parseInt(d.x) + "時"),
            datasets: [
                {
                    label: opts.label,
                    data: data.map((d) => d.y),
                    backgroundColor: `rgba(${opts.color}, 0.6)`,
                    borderColor: `rgb(${opts.color})`,
                    borderWidth: 2,
                    outlierColor: "rgb(239, 68, 68)",
                    medianColor: "rgb(255, 193, 7)",
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: opts.axisLabel },
                },
                x: {
                    title: { display: true, text: "時刻" },
                    ticks: { maxTicksLimit: 12, maxRotation: 45 },
                },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const stats = context.parsed;
                            return [
                                "最小値: " + stats.min.toFixed(opts.digits) + opts.unit,
                                "第1四分位: " + stats.q1.toFixed(opts.digits) + opts.unit,
                                "中央値: " + stats.median.toFixed(opts.digits) + opts.unit,
                                "第3四分位: " + stats.q3.toFixed(opts.digits) + opts.unit,
                                "最大値: " + stats.max.toFixed(opts.digits) + opts.unit,
                                "外れ値数: " + stats.outliers.length,
                            ];
                        },
                    },
                },
            },
        },
    });
}

function makeTimeseriesChart(canvasId, timeseries, opts) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !timeseries) {
        return;
    }

    const timestamps = timeseries.map((d) => d.timestamp);
    const rightAxis = {
        type: "linear",
        display: true,
        position: "right",
        title: { display: true, text: opts.rightAxis.title },
        grid: { drawOnChartArea: false },
    };
    if (opts.rightAxis.min !== undefined) rightAxis.min = opts.rightAxis.min;
    if (opts.rightAxis.max !== undefined) rightAxis.max = opts.rightAxis.max;

    new Chart(ctx, {
        type: "line",
        data: {
            labels: timestamps,
            datasets: opts.datasets.map((ds) => ({
                label: ds.label,
                data: timeseries.map((d) => (d[ds.column] != null ? d[ds.column] * ds.scale : null)),
                borderColor: `rgba(${ds.color}, 1)`,
                backgroundColor: `rgba(${ds.color}, 0.1)`,
                tension: 0.1,
                spanGaps: true,
                yAxisID: ds.axis,
            })),
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            scales: {
                y: {
                    type: "linear",
                    display: true,
                    position: "left",
                    title: { display: true, text: opts.leftAxis.title },
                },
                y1: rightAxis,
                x: {
                    title: { display: true, text: "時刻" },
                    ticks: {
                        maxTicksLimit: Math.max(6, Math.min(20, Math.floor(timestamps.length / 10))),
                        maxRotation: 45,
                        minRotation: 0,
                        autoSkip: true,
                        autoSkipPadding: 20,
                        callback: makeTimestampTickFormatter(timestamps),
                    },
                },
            },
        },
    });
}

function makeScatterChart(canvasId, pair, opts) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !pair) {
        return;
    }

    const points = pair.x.map((x, i) => ({ x: x, y: pair.y[i] * opts.yScale }));
    const r = calculateCorrelation(pair.x, pair.y);

    new Chart(ctx, {
        type: "scatter",
        data: {
            datasets: [
                {
                    label: `${opts.name} (r=${r.toFixed(3)})`,
                    data: points,
                    backgroundColor: `rgba(${opts.color}, 0.6)`,
                    borderColor: `rgba(${opts.color}, 1)`,
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { title: { display: true, text: opts.xLabel } },
                y: { title: { display: true, text: opts.yLabel } },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: function (context) {
                            return `データポイント: ${context.length}個`;
                        },
                        label: function (context) {
                            return [
                                `${opts.xName}: ${context.parsed.x.toFixed(1)}${opts.xUnit}`,
                                `${opts.yName}: ${context.parsed.y.toFixed(1)}${opts.yUnit}`,
                                `相関係数: ${r.toFixed(3)}`,
                            ];
                        },
                        afterLabel: function () {
                            return correlationStrengthLabel(r);
                        },
                    },
                },
            },
        },
    });
}

function makeEnergySavingsChart(canvasId, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
        return;
    }

    if (!data || !data.valid || !data.labels || data.labels.length === 0) {
        // データ不足時はチャートの代わりにメッセージを表示する
        const note = document.createElement("p");
        note.className = "has-text-centered has-text-grey";
        note.textContent = "データ不足のため表示できません";
        ctx.parentElement.replaceChild(note, ctx);
        return;
    }

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: "散水あり 平均消費電力（W）",
                    data: data.power_on,
                    backgroundColor: "rgba(52, 152, 219, 0.6)",
                    borderColor: "rgb(52, 152, 219)",
                    borderWidth: 1,
                },
                {
                    label: "散水なし 平均消費電力（W）",
                    data: data.power_off,
                    backgroundColor: "rgba(149, 165, 166, 0.6)",
                    borderColor: "rgb(149, 165, 166)",
                    borderWidth: 1,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            scales: {
                x: { title: { display: true, text: "外気温" } },
                y: { beginAtZero: true, title: { display: true, text: "平均消費電力（W）" } },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const counts = context.datasetIndex === 0 ? data.on_counts : data.off_counts;
                            const value =
                                context.parsed.y == null ? "データ不足" : context.parsed.y.toFixed(0) + " W";
                            return `${context.dataset.label}: ${value}（サンプル数 ${counts[context.dataIndex]}）`;
                        },
                    },
                },
            },
        },
    });
}

function renderCharts(chartData) {
    for (const cfg of BOXPLOT_CHARTS) {
        makeBoxplotChart(cfg.canvasId, chartData[cfg.key], cfg);
    }
    for (const cfg of TIMESERIES_CHARTS) {
        makeTimeseriesChart(cfg.canvasId, chartData.timeseries, cfg);
    }
    for (const cfg of SCATTER_CHARTS) {
        makeScatterChart(cfg.canvasId, chartData.correlation && chartData.correlation[cfg.key], cfg);
    }
    makeEnergySavingsChart("energySavingsChart", chartData.energy_savings);
}

// パーマリンク機能
function initializePermalinks() {
    document.querySelectorAll(".permalink-icon[data-permalink]").forEach((icon) => {
        icon.addEventListener("click", () => copyPermalink(icon.dataset.permalink));
    });

    // ページ読み込み時にハッシュがある場合はスクロール
    if (window.location.hash) {
        const element = document.querySelector(window.location.hash);
        if (element) {
            setTimeout(() => {
                element.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 500);
        }
    }
}

function copyPermalink(sectionId) {
    const url = window.location.origin + window.location.pathname + "#" + sectionId;

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard
            .writeText(url)
            .then(() => {
                showCopyNotification();
            })
            .catch((err) => {
                console.error("Failed to copy: ", err);
                fallbackCopyToClipboard(url);
            });
    } else {
        fallbackCopyToClipboard(url);
    }

    window.history.replaceState(null, null, "#" + sectionId);
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
        document.execCommand("copy");
        showCopyNotification();
    } catch (err) {
        console.error("Fallback: Failed to copy", err);
        prompt("URLをコピーしてください:", text);
    }

    document.body.removeChild(textArea);
}

function showCopyNotification() {
    const notification = document.createElement("div");
    notification.textContent = "パーマリンクをコピーしました！";
    notification.className = "copy-notification";

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = "0";
        setTimeout(() => {
            if (notification.parentNode) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

document.addEventListener("DOMContentLoaded", () => {
    initializePermalinks();

    const apiUrl = document.body.dataset.apiUrl;
    fetch(apiUrl)
        .then((response) => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(renderCharts)
        .catch((err) => {
            console.error("チャートデータの取得に失敗しました", err);
        });
});
