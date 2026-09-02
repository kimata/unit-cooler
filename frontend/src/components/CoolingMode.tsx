import React, { useState, useEffect, useCallback, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { API_ENDPOINT } from "../lib/api";
import type * as ApiResponse from "../lib/ApiResponse";
import { useApi } from "../hooks/useApi";
import { useOverride } from "../hooks/useOverride";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { Loading } from "./common/Loading";
import { ProgressBar } from "./common/ProgressBar";
import { Unit } from "./common/Unit";
import { OverrideControl } from "./OverrideControl";
import { AdjustmentsVerticalIcon, MoonIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
    logUpdateTrigger: number;
    // 停止・再開操作後に Actuator の実効状態を追いかけるための stat 再取得
    refetchStat: () => Promise<void>;
};

// Duty 表示エリアの状態。stopping / resuming は操作直後の遷移中（実効状態の反映待ち）。
type DutyPhase = "countdown" | "stopping" | "resuming" | "suspended-override" | "suspended-hazard";

const Spinner = () => (
    <span
        className="inline-block size-4 border-2 border-gray-300 border-t-gray-500 rounded-full animate-spin"
        aria-hidden="true"
    />
);

const emptyValveStatus: ApiResponse.ValveStatus = {
    state: "CLOSE",
    state_value: 0,
    duration: 0,
};

const emptyFlowStatus: ApiResponse.FlowStatus = {
    flow: 0,
};

const CoolingMode = React.memo(({ isReady, stat, logUpdateTrigger, refetchStat }: Props) => {
    // カウントダウンの終了予定時刻（ms）。null はカウントダウンなし。
    // 「残り秒を毎秒デクリメント」ではなく終了時刻基準で毎回計算することで、
    // setInterval の遅延・バックグラウンドタブによるドリフトを防ぐ。
    const [deadlineMs, setDeadlineMs] = useState<number | null>(null);

    // Actuator 側で Duty 制御が停止されているか（手動オーバーライド or ハザード）。
    // stat.mode.duty は Controller の生メッセージ由来でこれらを反映しないため、
    // ActuatorStatus の実効状態で判定する（未受信・鮮度切れで null の場合は判定しない）。
    const overrideActive = stat.actuator_status?.override_active === true;
    const hazardDetected = stat.actuator_status?.hazard_detected === true;

    const {
        override,
        loading: overrideLoading,
        pending: overridePending,
        postError: overridePostError,
        pause: overridePause,
        resume: overrideResume,
    } = useOverride(stat.actuator_status != null ? overrideActive : null, refetchStat);

    // 表示フェーズの決定。遷移中（pending）は実効状態より優先して「処理中」を出す。
    const dutyPhase: DutyPhase = hazardDetected
        ? "suspended-hazard"
        : overridePending === "resume"
          ? "resuming"
          : overridePending === "stop" && !overrideActive
            ? "stopping"
            : overrideActive
              ? "suspended-override"
              : "countdown";
    const dutySuspended = dutyPhase !== "countdown";
    const [remainingTime, setRemainingTime] = useState(0);
    const [currentFlow, setCurrentFlow] = useState(0);

    const {
        data: valveStatus,
        loading: valveLoading,
        error: valveError,
        refetch: refetchValveStatus,
    } = useApi(`${API_ENDPOINT}/proxy/json/api/valve_status`, emptyValveStatus, { immediate: isReady });

    const { data: flowStatus, refetch: refetchFlowStatus } = useApi(
        `${API_ENDPOINT}/proxy/json/api/get_flow`,
        emptyFlowStatus,
        { immediate: false }
    );

    // Refetch valve status when log update event occurs
    // stat.mode?.duty?.enable is intentionally excluded to only trigger on logUpdateTrigger changes
    useEffect(() => {
        if (isReady && stat.mode?.duty?.enable) {
            refetchValveStatus();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [logUpdateTrigger, isReady, refetchValveStatus]);

    // バルブ状態の更新時に終了予定時刻を再計算する
    useEffect(() => {
        if (!isReady || !stat.mode?.duty?.enable || valveLoading || dutySuspended) {
            setDeadlineMs(null);
            return;
        }

        const isOpen = valveStatus.state === "OPEN";
        const maxDuration = isOpen ? (stat.mode?.duty?.on_sec ?? 0) : (stat.mode?.duty?.off_sec ?? 0);
        const remaining = Math.max(0, maxDuration - valveStatus.duration);

        setDeadlineMs(Date.now() + remaining * 1000);
    }, [isReady, stat.mode?.duty?.enable, stat.mode?.duty?.on_sec, stat.mode?.duty?.off_sec, valveStatus, valveLoading, dutySuspended]);

    // 停止・ハザード状態からカウントダウン表示に復帰したとき、バルブ状態を取り直して
    // カウントダウンの起点（経過時間）を最新化する
    const prevDutySuspendedRef = useRef(dutySuspended);
    useEffect(() => {
        if (prevDutySuspendedRef.current && !dutySuspended) {
            refetchValveStatus();
        }
        prevDutySuspendedRef.current = dutySuspended;
    }, [dutySuspended, refetchValveStatus]);

    // 終了時刻基準のリアルタイムカウントダウン
    useEffect(() => {
        if (deadlineMs == null) {
            setRemainingTime(0);
            return;
        }

        const update = () => {
            setRemainingTime(Math.max(0, Math.round((deadlineMs - Date.now()) / 1000)));
        };

        update();
        const timer = setInterval(update, 1000);
        return () => clearInterval(timer);
    }, [deadlineMs]);

    // NOTE: currentFlow を依存配列に入れると、流量更新（毎秒）のたびにこの effect が
    // 再生成され interval が張り直されて約 2 req/s になる。ref 経由で最新値を読み、
    // interval は valve 状態の変化時のみ生成する。
    const currentFlowRef = useRef(currentFlow);
    useEffect(() => {
        currentFlowRef.current = currentFlow;
    }, [currentFlow]);

    // Update flow when valve is OPEN or when CLOSE but flow > 0
    useEffect(() => {
        const shouldPoll =
            valveStatus.state === "OPEN" || (valveStatus.state === "CLOSE" && currentFlowRef.current > 0);
        if (!shouldPoll) {
            return;
        }

        refetchFlowStatus();
        const flowTimer = setInterval(() => {
            // CLOSE になり流量が 0 まで落ちたらポーリングを止める
            if (valveStatus.state === "CLOSE" && currentFlowRef.current <= 0) {
                clearInterval(flowTimer);
                return;
            }
            refetchFlowStatus();
        }, 1000);
        return () => clearInterval(flowTimer);
    }, [valveStatus.state, refetchFlowStatus]);

    // Update currentFlow state when flowStatus changes
    useEffect(() => {
        if (flowStatus && flowStatus.flow !== undefined) {
            setCurrentFlow(flowStatus.flow);
        }
    }, [flowStatus]);

    const formatTime = useCallback((seconds: number): string => {
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds) % 60;
        return `${minutes}:${secs.toString().padStart(2, "0")}`;
    }, []);

    const dutyInfo = (mode: ApiResponse.Mode) => (
        <div className="w-full">
            <div className="flex">
                <div className="w-1/2">
                    <span className="mr-1">Open:</span>
                    <AnimatedNumber
                        value={Math.round((mode.duty?.on_sec ?? 0) / 60)}
                        decimals={0}
                        className="text-3xl font-light digit"
                    />
                    <Unit>min</Unit>
                </div>
                <div className="w-1/2">
                    <span className="mr-1">Close:</span>
                    <AnimatedNumber
                        value={Math.round((mode.duty?.off_sec ?? 0) / 60)}
                        decimals={0}
                        className="text-3xl font-light digit"
                    />
                    <Unit>min</Unit>
                </div>
            </div>
        </div>
    );

    const valveStatusDisplay = () => {
        if (valveLoading || valveError || !stat.mode?.duty?.enable) {
            return null;
        }

        const isOpen = valveStatus.state === "OPEN";
        const maxDuration = isOpen ? (stat.mode?.duty?.on_sec ?? 0) : (stat.mode?.duty?.off_sec ?? 0);
        const progress = maxDuration > 0 ? ((maxDuration - remainingTime) / maxDuration) * 100 : 0;

        return (
            <div className="mt-3">
                {/* Valve Status */}
                <div className="flex items-center mb-2">
                    <div className="w-full text-center">
                        <span
                            className={`inline-flex items-center justify-center gap-2 px-3 py-1 rounded text-sm text-white ${
                                isOpen ? "bg-[#5e7e9b]" : "bg-gray-400"
                            }`}
                        >
                            <span>{valveStatus.state}</span>
                            {(isOpen || currentFlow > 0) && (
                                <span className="font-normal text-sm">
                                    <AnimatedNumber value={currentFlow} decimals={2} duration={0.9} />
                                    <Unit>L/min</Unit>
                                </span>
                            )}
                        </span>
                    </div>
                </div>

                {/* Progress Bar / 停止・再開の遷移中 / 強制停止中の表示（クロスフェードで切り替え） */}
                <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                        key={dutyPhase}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.25 }}
                    >
                        {dutyPhase === "stopping" && (
                            <div
                                className="flex items-center justify-center gap-2 mb-1"
                                data-testid="duty-stopping"
                            >
                                <Spinner />
                                <small className="text-gray-500">停止処理中です…</small>
                            </div>
                        )}
                        {dutyPhase === "resuming" && (
                            <div
                                className="flex items-center justify-center gap-2 mb-1"
                                data-testid="duty-resuming"
                            >
                                <Spinner />
                                <small className="text-gray-500">再開処理中です…</small>
                            </div>
                        )}
                        {(dutyPhase === "suspended-override" || dutyPhase === "suspended-hazard") && (
                            <div className="text-center mb-1" data-testid="duty-suspended">
                                <small className="text-gray-500">
                                    {dutyPhase === "suspended-hazard"
                                        ? "ハザード検知のため散水を停止しています"
                                        : "手動停止中のため Duty 制御を停止しています"}
                                </small>
                            </div>
                        )}
                        {dutyPhase === "countdown" && (
                            <>
                                <div className="flex items-center mb-1">
                                    <ProgressBar
                                        fillPercent={progress}
                                        animationKey={`${valveStatus.state}-${maxDuration}-${valveStatus.duration}`}
                                        ariaValueNow={progress}
                                        ariaValueMax={100}
                                        overlayClassName="text-gray-400"
                                    >
                                        <small className="mr-2">残り</small>
                                        <b>{formatTime(remainingTime)}</b>
                                    </ProgressBar>
                                </div>

                                {/* Warning Message */}
                                {remainingTime <= 5 && remainingTime > 0 && (
                                    <div className="text-center mt-1">
                                        <small className="text-yellow-500">まもなく切り替え</small>
                                    </div>
                                )}
                                {/* 残り 0 秒はバルブの切り替え反映待ち（Actuator の制御ループと
                                    作動ログ経由の再取得を待つ間、固まって見えないようにする） */}
                                {remainingTime === 0 && (
                                    <div
                                        className="flex items-center justify-center gap-2 mt-1"
                                        data-testid="duty-switching"
                                    >
                                        <Spinner />
                                        <small className="text-gray-500">切り替え待ちです…</small>
                                    </div>
                                )}
                            </>
                        )}
                    </motion.div>
                </AnimatePresence>
            </div>
        );
    };

    const modeInfo = (mode: ApiResponse.Mode) => {
        return (
            <div data-testid="cooling-info">
                <div className="text-6xl font-light align-middle ml-1">
                    <AnimatedNumber value={mode.mode_index} decimals={0} className="font-bold digit" />
                </div>
                {/* 夜間停止によるモード 0 固定中の表示（モード 0 の理由が分かるように） */}
                {mode.night_stop && (
                    <div className="mt-1 mb-2 flex justify-center" data-testid="night-stop-badge">
                        <span className="inline-flex items-center gap-1 px-3 py-1 rounded bg-indigo-50 border border-indigo-200 text-indigo-600 text-sm">
                            <MoonIcon className="size-4" />
                            夜間停止中
                        </span>
                    </div>
                )}
                {dutyInfo(mode)}
                {valveStatusDisplay()}
            </div>
        );
    };

    return (
        <DashboardCard title="現在の冷却モード" icon={<AdjustmentsVerticalIcon className="size-5 text-gray-500" />}>
            <CardBody>
                {isReady || stat.mode.mode_index !== 0 ? modeInfo(stat.mode) : <Loading size="large" />}
                {/* 散水の手動一時停止（オーバーライド）。モード表示のロード状態とは独立に描画する */}
                <OverrideControl
                    override={override}
                    loading={overrideLoading}
                    pending={overridePending}
                    postError={overridePostError}
                    onPause={overridePause}
                    onResume={overrideResume}
                />
            </CardBody>
        </DashboardCard>
    );
});

CoolingMode.displayName = "CoolingMode";

export { CoolingMode };
