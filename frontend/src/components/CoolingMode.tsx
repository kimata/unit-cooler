import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";

import type * as ApiResponse from "../lib/ApiResponse";
import { useApi } from "../hooks/useApi";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { Loading } from "./common/Loading";
import { Unit } from "./common/Unit";
import { AdjustmentsVerticalIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
    logUpdateTrigger: number;
};

const CoolingMode = React.memo(({ isReady, stat, logUpdateTrigger }: Props) => {
    const API_ENDPOINT = "/unit-cooler/api";
    const [remainingTime, setRemainingTime] = useState(0);
    const [currentFlow, setCurrentFlow] = useState(0);

    const emptyValveStatus: ApiResponse.ValveStatus = {
        state: "CLOSE",
        state_value: 0,
        duration: 0,
    };

    const emptyFlowStatus: ApiResponse.FlowStatus = {
        flow: 0,
    };

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

    // Calculate remaining time
    useEffect(() => {
        if (!isReady || !stat.mode?.duty?.enable || valveLoading) {
            setRemainingTime(0);
            return;
        }

        const isOpen = valveStatus.state === "OPEN";
        const maxDuration = isOpen ? (stat.mode?.duty?.on_sec ?? 0) : (stat.mode?.duty?.off_sec ?? 0);
        const elapsed = valveStatus.duration;
        const remaining = Math.max(0, maxDuration - elapsed);

        setRemainingTime(remaining);
    }, [isReady, stat.mode?.duty?.enable, stat.mode?.duty?.on_sec, stat.mode?.duty?.off_sec, valveStatus, valveLoading]);

    // Real-time countdown update
    useEffect(() => {
        if (remainingTime <= 0) return;

        const timer = setInterval(() => {
            setRemainingTime((prev) => Math.max(0, prev - 1));
        }, 1000);

        return () => clearInterval(timer);
    }, [remainingTime]);

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

                {/* Progress Bar */}
                <div className="flex items-center mb-1">
                    <div className="w-full">
                        <div className="relative">
                            <div className="w-full bg-gray-200 rounded overflow-hidden h-8">
                                <motion.div
                                    key={`${valveStatus.state}-${maxDuration}-${valveStatus.duration}`}
                                    className="h-full bg-gray-500 transition-all duration-500"
                                    role="progressbar"
                                    initial={{ width: "0%" }}
                                    animate={{ width: `${Math.max(0, progress)}%` }}
                                    transition={{ duration: 0.5, ease: "easeOut" }}
                                    aria-valuenow={progress}
                                    aria-valuemin={0}
                                    aria-valuemax={100}
                                />
                            </div>
                            <div className="absolute top-1/2 -translate-y-1/2 right-[5%] text-xl digit text-gray-400">
                                <small className="mr-2">残り</small>
                                <b>{formatTime(remainingTime)}</b>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Warning Message */}
                {remainingTime <= 5 && remainingTime > 0 && (
                    <div className="text-center mt-1">
                        <small className="text-yellow-500">まもなく切り替え</small>
                    </div>
                )}
            </div>
        );
    };

    const modeInfo = (mode: ApiResponse.Mode) => {
        return (
            <div data-testid="cooling-info">
                <div className="text-6xl font-light align-middle ml-1">
                    <AnimatedNumber value={mode.mode_index} decimals={0} className="font-bold digit" />
                </div>
                {dutyInfo(mode)}
                {valveStatusDisplay()}
            </div>
        );
    };

    return (
        <DashboardCard title="現在の冷却モード" icon={<AdjustmentsVerticalIcon className="size-5 text-gray-500" />}>
            <CardBody>
                {isReady || stat.mode.mode_index !== 0 ? modeInfo(stat.mode) : <Loading size="large" />}
            </CardBody>
        </DashboardCard>
    );
});

CoolingMode.displayName = "CoolingMode";

export { CoolingMode };
