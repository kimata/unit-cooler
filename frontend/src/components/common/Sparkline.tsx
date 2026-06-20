import React from "react";

type Props = {
    values: number[];
    min: number;
    max: number;
};

// センサー値列の背景に敷く淡いグレーの推移グラフ。
// 行（セル）の上端が過去期間の最大値、下端が最小値に対応する。
// 現在値（系列末尾）は濃いめの点で強調する。
const Sparkline = React.memo(({ values, min, max }: Props) => {
    if (values.length === 0) {
        return null;
    }

    const range = max - min;
    // 値を 0..1 に正規化（値域が 0 のときは中央に寄せる）
    const norm = (v: number) => (range === 0 ? 0.5 : (v - min) / range);

    const n = values.length;
    const xAt = (i: number) => (n === 1 ? 100 : (i / (n - 1)) * 100); // %
    const yAt = (v: number) => (1 - norm(v)) * 100; // % (max→0=上端, min→100=下端)

    const points = values.map((v, i) => `${xAt(i)},${yAt(v)}`).join(" ");
    const areaPoints = `0,100 ${points} 100,100`;

    const lastX = xAt(n - 1);
    const lastY = yAt(values[n - 1]);

    return (
        // inset-y で上下に余白を設け、隣接行のグラフ同士が接触しないようにする。
        // 右端は列端から少し内側(right-2)に寄せ、末尾の現在値プロット(円)が
        // 列の overflow-hidden で右半分が欠けないようにする。
        <div className="absolute inset-y-1.5 left-0 right-2 pointer-events-none" aria-hidden="true">
            <svg
                className="absolute inset-0 w-full h-full"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
            >
                <polygon points={areaPoints} fill="rgb(107 114 128)" fillOpacity="0.05" />
                <polyline
                    points={points}
                    fill="none"
                    stroke="rgb(107 114 128)"
                    strokeOpacity="0.22"
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                />
            </svg>
            {/* preserveAspectRatio=none による歪みを避けるため、現在値の点は絶対配置の円で描く */}
            <span
                className="absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-gray-400"
                style={{ left: `${lastX}%`, top: `${lastY}%` }}
            />
        </div>
    );
});

Sparkline.displayName = "Sparkline";

export { Sparkline };
