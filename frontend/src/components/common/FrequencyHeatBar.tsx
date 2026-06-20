import React from "react";

type Props = {
    // 過去期間の値の系列（時刻順は問わない。頻度分布のみ使用）
    values: number[];
    // 軸の最大値（電力バーと同じスケールに合わせる）
    max: number;
    // ビン数（横方向の分解能。多いほどグラデーションが滑らか）
    bins?: number;
    // 濃淡の色（RGB 値のカンマ区切り）。既定は slate-600
    colorRgb?: string;
    // 最頻ビンの不透明度（0〜1）
    maxAlpha?: number;
    // 配置・サイズ（呼び出し側で absolute inset-0 等を指定）
    className?: string;
};

// 値の度数分布を横方向の濃淡で表す背景レイヤー。
// 左端=0、右端=max に対応し、濃いほどその値帯にいた頻度が高い。
// ProgressBar の trackBackground として全面に敷き、半透明の塗りと重ねて使う。
const FrequencyHeatBar = React.memo(
    ({ values, max, bins = 48, colorRgb = "71, 85, 105", maxAlpha = 0.6, className = "" }: Props) => {
        if (values.length === 0 || max <= 0) {
            return null;
        }

        const counts = new Array<number>(bins).fill(0);
        for (const v of values) {
            const idx = Math.min(bins - 1, Math.max(0, Math.floor((v / max) * bins)));
            counts[idx] += 1;
        }

        // 3-tap 平滑化でビン境界のガタつきをならし、滑らかなグラデーションにする
        const smoothed = counts.map(
            (c, i) => (counts[i - 1] ?? 0) * 0.25 + c * 0.5 + (counts[i + 1] ?? 0) * 0.25,
        );
        const peak = Math.max(...smoothed, 1);

        // 各ビン中心に色停止点を置き、CSS の補間で滑らかなグラデーションにする
        const stops = smoothed
            .map((c, i) => {
                const pct = bins === 1 ? 0 : (i / (bins - 1)) * 100;
                const alpha = (c / peak) * maxAlpha;
                return `rgba(${colorRgb}, ${alpha.toFixed(3)}) ${pct.toFixed(1)}%`;
            })
            .join(", ");

        return (
            <div
                className={className}
                style={{ backgroundImage: `linear-gradient(to right, ${stops})` }}
                aria-hidden="true"
            />
        );
    },
);

FrequencyHeatBar.displayName = "FrequencyHeatBar";

export { FrequencyHeatBar };
