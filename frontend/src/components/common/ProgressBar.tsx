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
    // トラック（背景）のクラス上書き（色・角丸）。既定は四隅丸の薄グレー
    trackClassName?: string;
    // 塗りつぶしのクラス上書き（色）。既定は中間グレー
    fillClassName?: string;
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
        trackClassName = "bg-gray-200 rounded",
        fillClassName = "bg-gray-500",
    }: Props) => (
        <div className="relative w-full">
            <div className={`w-full overflow-hidden h-8 ${trackClassName}`}>
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
