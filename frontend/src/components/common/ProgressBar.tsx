import React from "react";
import { motion } from "framer-motion";

type Props = {
    // 塗りつぶし幅（0-100 のパーセント）
    fillPercent: number;
    // アニメーション開始時の幅（パーセント、既定 0）
    initialPercent?: number;
    // 塗りつぶしアニメーションの秒数（既定 0.5）
    durationSec?: number;
    ariaValueNow: number;
    ariaValueMax: number;
    // 値が変わったら最初から再アニメーションさせたい場合に渡す（motion の key）
    animationKey?: string | number;
    // バー上に重ねるオーバーレイ（残り時間や数値など）
    children?: React.ReactNode;
    // オーバーレイの追加クラス（色など）
    overlayClassName?: string;
    // トラック（背景）のクラス上書き（色）。既定は薄グレー
    trackClassName?: string;
    // 塗りつぶしのクラス上書き（色）。既定は中間グレー
    fillClassName?: string;
    // トラックの下に同じ角丸枠内で描く要素（頻度ヒートマップ等）。
    // 指定すると枠全体が一体の部品になり、オーバーレイも枠全体の中央に寄る。
    footer?: React.ReactNode;
};

// バーのトラック + アニメーションする塗りつぶし + オーバーレイの共通コンポーネント。
// AirConditioner（消費電力）と CoolingMode（バルブ残り時間）で共有する。
const ProgressBar = React.memo(
    ({
        fillPercent,
        initialPercent = 0,
        durationSec = 0.5,
        ariaValueNow,
        ariaValueMax,
        animationKey,
        children,
        overlayClassName = "",
        trackClassName = "bg-gray-200",
        fillClassName = "bg-gray-500",
        footer,
    }: Props) => (
        // rounded + overflow-hidden を最外枠に置くことで、トラックと footer を
        // 1 つの角丸矩形に内包し一体の部品として見せる。
        <div className="relative w-full overflow-hidden rounded">
            <div className={`w-full h-8 ${trackClassName}`}>
                <motion.div
                    key={animationKey}
                    className={`h-full transition-all duration-500 ${fillClassName}`}
                    role="progressbar"
                    aria-valuenow={ariaValueNow}
                    aria-valuemin={0}
                    aria-valuemax={ariaValueMax}
                    initial={{ width: `${initialPercent}%` }}
                    animate={{ width: `${Math.max(0, fillPercent)}%` }}
                    transition={{ duration: durationSec, ease: "easeOut" }}
                />
            </div>
            {footer}
            {children != null && (
                <div className={`absolute top-1/2 -translate-y-1/2 right-[5%] text-xl digit ${overlayClassName}`}>
                    {children}
                </div>
            )}
        </div>
    )
);

ProgressBar.displayName = "ProgressBar";

export { ProgressBar };
