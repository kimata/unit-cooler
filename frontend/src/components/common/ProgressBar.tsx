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
    // 塗りつぶしのクラス上書き（色）。既定は中間グレー。
    // 背景レイヤーを透かしたい場合は半透明色（例: bg-gray-500/80）を渡す。
    fillClassName?: string;
    // 塗りの右端（＝現在値の位置）に重ねる縦線のクラス（幅・色）。
    // 指定時のみ描画。塗りに追従するので現在値が読み取りやすくなる（例: "w-[1.5px] bg-gray-800"）。
    fillCursorClassName?: string;
    // トラックの全面背景に敷く要素（頻度ヒートマップ等）。塗りより下に描画され、
    // 半透明の塗りと組み合わせると未塗り部・塗り部の両方に分布が透ける。
    trackBackground?: React.ReactNode;
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
        fillCursorClassName,
        trackBackground,
    }: Props) => (
        <div className={`relative w-full overflow-hidden rounded h-8 ${trackClassName}`}>
            {/* 背景レイヤー（ヒートマップ等）。塗りより下に敷く */}
            {trackBackground}
            <motion.div
                key={animationKey}
                className={`absolute inset-y-0 left-0 transition-all duration-500 ${fillClassName}`}
                role="progressbar"
                aria-valuenow={ariaValueNow}
                aria-valuemin={0}
                aria-valuemax={ariaValueMax}
                initial={{ width: `${initialPercent}%` }}
                animate={{ width: `${Math.max(0, fillPercent)}%` }}
                transition={{ duration: durationSec, ease: "easeOut" }}
            >
                {/* 塗りの右端（現在値の位置）に重ねる縦線。塗りに追従する */}
                {fillCursorClassName != null && (
                    <div
                        className={`absolute inset-y-0 right-0 -translate-x-px ${fillCursorClassName}`}
                        aria-hidden="true"
                    />
                )}
            </motion.div>
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
