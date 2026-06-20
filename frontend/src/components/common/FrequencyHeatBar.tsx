import React from "react";

type Props = {
    // 過去期間の値の系列（時刻順は問わない。頻度分布のみ使用）
    values: number[];
    // 軸の最大値（電力バーと同じスケールに合わせる）
    max: number;
    // ビン数（横方向の分解能。多いほどグラデーションが滑らか）
    bins?: number;
    className?: string;
};

// 値の度数分布を横方向の濃淡（滞在頻度ヒートバー）で表す細い帯。
// 左端=0、右端=max に対応し、濃いほどその値帯にいた頻度が高い。
// 棒グラフ直下に隙間なく重ねる前提で、上端は角丸なし・下端のみ角丸にする。
const FrequencyHeatBar = React.memo(({ values, max, bins = 48, className = "" }: Props) => {
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

    // 各ビン中心に色停止点を置き、CSS の補間で滑らかなグラデーションにする。
    // 色は棒グラフの塗り(slate-600 = 71,85,105)と揃え、一体のグラフに見せる。
    const stops = smoothed
        .map((c, i) => {
            const pct = bins === 1 ? 0 : (i / (bins - 1)) * 100;
            const alpha = (c / peak) * 0.75; // 頻度に比例した濃さ（最大 0.75）
            return `rgba(71, 85, 105, ${alpha.toFixed(3)}) ${pct.toFixed(1)}%`;
        })
        .join(", ");

    return (
        // 角丸・土台色は親の枠(ProgressBar)が持つため、ここでは持たない
        <div
            className={`h-1 w-full bg-gray-200 ${className}`}
            style={{ backgroundImage: `linear-gradient(to right, ${stops})` }}
            aria-hidden="true"
        />
    );
});

FrequencyHeatBar.displayName = "FrequencyHeatBar";

export { FrequencyHeatBar };
