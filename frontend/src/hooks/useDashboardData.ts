import { useState, useEffect, useCallback } from "react";

import dayjs from "../lib/dayjs";
import type * as ApiResponse from "../lib/ApiResponse";
import { useApi } from "./useApi";
import { useEventSource } from "./useEventSource";

const API_ENDPOINT = "/unit-cooler/api";

// バックエンド (cooler_stat.py: CoolerStats.idle) が常に非 null・全フィールドを返すため、
// 初期プレースホルダもそれに合わせた完全な形を持つ。
const emptyStat: ApiResponse.Stat = {
    cooler_status: { message: "", status: 0 },
    outdoor_status: { message: "", status: 0 },
    mode: {
        duty: { enable: false, off_sec: 0, on_sec: 0 },
        mode_index: 0,
        state: 0,
    },
    sensor: { temp: [], humi: [], lux: [], solar_rad: [], rain: [], power: [] },
};

// センサー背景グラフの初期値（未取得時は各種別が欠落した空オブジェクト）
const emptySensorGraph: ApiResponse.SensorGraph = {};

// NOTE: 空配列にすることで初回ロード中（isReady=false）に Loading 分岐へ入る (BUG #13)。
const emptyWatering: ApiResponse.WateringResponse = { watering: [] };
const emptyLog: ApiResponse.Log = { data: [], last_time: 0 };
const emptySysInfo: ApiResponse.SysInfo = {
    date: "",
    image_build_date: "",
    load_average: "?",
    uptime: "",
};

// 各データ取得元のエラーに付ける日本語ラベル
const ERROR_LABELS = [
    "統計データ",
    "散水データ",
    "ログデータ",
    "システム情報",
    "アクチュエータ情報",
] as const;

// ダッシュボードのデータ取得・派生状態をまとめて提供するフック。
// API 呼び出し・SSE 購読・ローディング/エラー集約を App から分離する。
export function useDashboardData() {
    const [logUpdateTrigger, setLogUpdateTrigger] = useState(0);
    const [updateTime, setUpdateTime] = useState("Unknown");
    const [isLogFirstLoad, setIsLogFirstLoad] = useState(true);

    const {
        data: stat,
        loading: statLoading,
        error: statError,
        refetch: refetchStat,
    } = useApi(`${API_ENDPOINT}/stat`, emptyStat, { interval: 58000 });

    const {
        data: wateringData,
        loading: wateringLoading,
        error: wateringError,
        refetch: refetchWatering,
    } = useApi(`${API_ENDPOINT}/watering`, emptyWatering, { interval: 58000 });

    const { data: sensorGraph } = useApi(`${API_ENDPOINT}/sensor_graph`, emptySensorGraph, {
        interval: 58000,
    });

    const {
        data: log,
        loading: logLoading,
        error: logError,
        refetch: refetchLog,
    } = useApi(`${API_ENDPOINT}/proxy/json/api/log_view`, emptyLog, { retryInterval: 10000 });

    const { data: sysInfo, error: sysInfoError } = useApi(`${API_ENDPOINT}/sysinfo`, emptySysInfo, {
        interval: 58000,
    });

    const { data: actuatorSysInfo, error: actuatorSysInfoError } = useApi(
        `${API_ENDPOINT}/proxy/json/api/sysinfo`,
        emptySysInfo,
        { interval: 58000 }
    );

    // SSE による更新通知（ログ更新時に stat / log を再取得し更新時刻を刻む）
    useEventSource(`${API_ENDPOINT}/proxy/event/api/event`, {
        onMessage: (e) => {
            if (e.data === "log") {
                refetchLog();
                refetchStat();
                setUpdateTime(dayjs().format("llll"));
                setLogUpdateTrigger((prev) => prev + 1);
            }
        },
    });

    // 初回ログロード完了を記録（レンダー中 setState を避けて effect で行う）
    useEffect(() => {
        if (!logLoading) {
            setIsLogFirstLoad(false);
        }
    }, [logLoading]);

    // stat 初回ロード時に更新日時を初期化する
    useEffect(() => {
        if (!statLoading) {
            setUpdateTime((prev) => (prev === "Unknown" ? dayjs().format("LLL") : prev));
        }
    }, [statLoading]);

    const isReady = !statLoading && !wateringLoading && !logLoading;
    const isLogReady = !logLoading || !isLogFirstLoad;

    const errorList = [statError, wateringError, logError, sysInfoError, actuatorSysInfoError];
    const firstErrorIndex = errorList.findIndex((e) => e);
    const hasError = firstErrorIndex !== -1;
    const errorMessage = hasError
        ? `${ERROR_LABELS[firstErrorIndex]}: ${errorList[firstErrorIndex]}`
        : "データの読み込みに失敗しました";

    const handleRetry = useCallback(() => {
        refetchStat();
        refetchWatering();
        refetchLog();
    }, [refetchStat, refetchWatering, refetchLog]);

    return {
        apiEndpoint: API_ENDPOINT,
        stat,
        wateringData,
        sensorGraph,
        log,
        sysInfo,
        actuatorSysInfo,
        isReady,
        isLogReady,
        logUpdateTrigger,
        updateTime,
        hasError,
        errorMessage,
        handleRetry,
    };
}
