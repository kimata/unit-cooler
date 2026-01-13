import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { ApiResponse } from "../lib/ApiResponse";
import { useApi } from "../hooks/useApi";
import { Loading } from "./common/Loading";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { SnowflakeIcon } from "./icons";

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
        refetch: refetchValveStatus
    } = useApi(`${API_ENDPOINT}/proxy/json/api/valve_status`, emptyValveStatus, {
        immediate: isReady
    });

    const {
        data: flowStatus,
        refetch: refetchFlowStatus
    } = useApi(`${API_ENDPOINT}/proxy/json/api/get_flow`, emptyFlowStatus, {
        immediate: false
    });

    // Refetch valve status when log update event occurs
    useEffect(() => {
        if (isReady && stat.mode?.duty?.enable) {
            refetchValveStatus();
        }
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
            setRemainingTime(prev => Math.max(0, prev - 1));
        }, 1000);

        return () => clearInterval(timer);
    }, [remainingTime]);

    // Update flow when valve is OPEN or when CLOSE but flow > 0
    useEffect(() => {
        if (valveStatus.state === "OPEN" || (valveStatus.state === "CLOSE" && currentFlow > 0)) {
            // Initial fetch
            refetchFlowStatus();

            // Update every second while OPEN or CLOSE with flow > 0
            const flowTimer = setInterval(() => {
                refetchFlowStatus();
            }, 1000);

            return () => clearInterval(flowTimer);
        }
    }, [valveStatus.state, refetchFlowStatus, currentFlow]);

    // Update currentFlow state when flowStatus changes
    useEffect(() => {
        if (flowStatus && flowStatus.flow !== undefined) {
            setCurrentFlow(flowStatus.flow);
        }
    }, [flowStatus]);

    const formatTime = useCallback((seconds: number): string => {
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds) % 60;
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }, []);

    const dutyInfo = (mode: ApiResponse.Mode) => {
        return (
            <div className="w-full">
                <div className="flex">
                    <div className="w-1/2">
                        <span className="mr-1">Open:</span>
                        <AnimatedNumber
                            value={Math.round((mode.duty?.on_sec ?? 0) / 60)}
                            decimals={0}
                            className="text-3xl font-light digit"
                        />
                        <span className="ml-1">min</span>
                    </div>
                    <div className="w-1/2">
                        <span className="mr-1">Close:</span>
                        <AnimatedNumber
                            value={Math.round((mode.duty?.off_sec ?? 0) / 60)}
                            decimals={0}
                            className="text-3xl font-light digit"
                        />
                        <span className="ml-1">min</span>
                    </div>
                </div>
            </div>
        );
    };

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
                            className="inline-flex items-center justify-center gap-2 px-3 py-1 rounded text-sm"
                            style={{
                                backgroundColor: isOpen ? '#5e7e9b' : '#adb5bd',
                                color: '#ffffff'
                            }}
                        >
                            <span>{valveStatus.state}</span>
                            {(isOpen || currentFlow > 0) && (
                                <span className="font-normal text-sm">
                                    <AnimatedNumber
                                        value={currentFlow}
                                        decimals={2}
                                        duration={0.9}
                                        className=""
                                    />
                                    <span className="ml-1">L/min</span>
                                </span>
                            )}
                        </span>
                    </div>
                </div>

                {/* Progress Bar */}
                <div className="flex items-center mb-1">
                    <div className="w-full">
                        <div className="progress-label-container">
                            <div className="progress" style={{ height: "2em" }}>
                                <motion.div
                                    key={`${valveStatus.state}-${maxDuration}-${valveStatus.duration}`}
                                    className="progress-bar bg-gray-500"
                                    role="progressbar"
                                    initial={{ width: "0%" }}
                                    animate={{ width: `${Math.max(0, progress)}%` }}
                                    transition={{ duration: 0.5, ease: "easeOut" }}
                                    aria-valuenow={progress}
                                    aria-valuemin={0}
                                    aria-valuemax={100}
                                />
                            </div>
                            <div className="progress-label digit">
                                <small style={{ color: '#adb5bd' }} className="mr-2">残り</small>
                                <b style={{ color: '#adb5bd' }}>
                                    {formatTime(remainingTime)}
                                </b>
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
        if (mode == null) {
            return <Loading size="large" />;
        }

        return (
            <div data-testid="cooling-info">
                <div className="text-6xl font-light align-middle ml-1">
                    <AnimatedNumber
                        value={mode.mode_index}
                        decimals={0}
                        className="font-bold digit"
                    />
                </div>
                {dutyInfo(mode)}
                {valveStatusDisplay()}
            </div>
        );
    };

    return (
        <div>
            <div className="text-center h-full">
                <div className="card shadow-sm h-full">
                    <div className="card-header">
                        <h4 className="my-0 font-normal">
                            <SnowflakeIcon className="size-5 text-gray-500" />
                            現在の冷却モード
                        </h4>
                    </div>
                    <div className="card-body">{isReady || stat.mode.mode_index !== 0 ? modeInfo(stat.mode) : <Loading size="large" />}</div>
                </div>
            </div>
        </div>
    );
});

CoolingMode.displayName = 'CoolingMode';

export { CoolingMode };
