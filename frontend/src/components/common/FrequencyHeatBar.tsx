import React from "react";

type Props = {
    // 過去期間の値の系列（時刻順は問わない。頻度分布のみ使用）
    values: number[];
    // 軸の最大値（電力バーと同じスケールに合わせる）
    max: number;
    // 現在値（はっきりした縦線で位置を示す）。null なら線を描かない
    current: number | null;
    // ビン数（横方向の分解能）
    bins?: number;
    className?: string;
};

// 値の度数分布を横方向の濃淡（滞在頻度ヒートバー）で表す細い帯。
// 左端=0、右端=max に対応し、各ビンの濃さがその値帯にいた頻度に比例する。
// 現在値は最前面の縦線で明示する。
const FrequencyHeatBar = React.memo(({ values, max, current, bins = 24, className = "" }: Props) => {
    if (values.length === 0 || max <= 0) {
        return null;
    }

    const counts = new Array<number>(bins).fill(0);
    for (const v of values) {
        const idx = Math.min(bins - 1, Math.max(0, Math.floor((v / max) * bins)));
        counts[idx] += 1;
    }
    const maxCount = Math.max(...counts);

    const currentPct =
        current != null ? Math.min(100, Math.max(0, (current / max) * 100)) : null;

    return (
        <div
            className={`relative h-2 w-full flex overflow-hidden rounded-sm bg-gray-100 ${className}`}
            aria-hidden="true"
        >
            {counts.map((count, i) => (
                <div
                    key={i}
                    className="h-full flex-1 bg-gray-500"
                    // 空ビンは透明、頻度が高いほど濃く（滞在頻度の濃淡）
                    style={{ opacity: maxCount === 0 ? 0 : (count / maxCount) * 0.85 }}
                />
            ))}
            {currentPct != null && (
                <span
                    className="absolute -top-0.5 -bottom-0.5 w-0.5 -translate-x-1/2 rounded-full bg-sky-500 shadow-sm"
                    style={{ left: `${currentPct}%` }}
                />
            )}
        </div>
    );
});

FrequencyHeatBar.displayName = "FrequencyHeatBar";

export { FrequencyHeatBar };
