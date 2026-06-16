import { useState, useMemo, useCallback } from "react";

import { GitHubIcon, ChartBarIcon } from "./components/icons";

import dayjs from "./lib/dayjs";

import { version as reactVersion } from "react";

import type * as ApiResponse from "./lib/ApiResponse";
import { useApi } from "./hooks/useApi";
import { useEventSource } from "./hooks/useEventSource";
import { ErrorMessage } from "./components/common/ErrorMessage";

import { Watering } from "./components/Watering";
import { History } from "./components/History";
import { CoolingMode } from "./components/CoolingMode";
import { AirConditioner } from "./components/AirConditioner";
import { Sensor } from "./components/Sensor";
import { Log } from "./components/Log";

// 日時文字列を整形する。空・未取得・"?" などの不正値は dayjs().isValid() で弾き "?" を返す。
function formatDateOrFallback(value: string | undefined, method: "format" | "fromNow"): string {
    const date = dayjs(value);
    if (!value || !date.isValid()) {
        return "?";
    }
    return method === "format" ? date.format("LLL") : date.fromNow();
}

function App() {
    const API_ENDPOINT = "/unit-cooler/api";
    const [logUpdateTrigger, setLogUpdateTrigger] = useState(0);

    const emptyStat: ApiResponse.Stat = {
        cooler_status: {
            message: "",
            status: 0,
        },
        outdoor_status: {
            message: "",
            status: 0,
        },
        mode: {
            duty: {
                enable: false,
                off_sec: 0,
                on_sec: 0,
            },
            mode_index: 0,
            state: 0,
        },
        sensor: {
            temp: [],
            humi: [],
            lux: [],
            solar_rad: [],
            rain: [],
            power: [],
        },
    };

    const emptyWatering: ApiResponse.WateringResponse = {
        watering: [
            {
                amount: 0,
                price: 0,
            },
        ],
    };
    const emptyLog: ApiResponse.Log = {
        data: [],
        last_time: 0,
    };

    const emptySysInfo: ApiResponse.SysInfo = {
        date: "",
        image_build_date: "",
        load_average: "?",
        uptime: ""
    };

    const [updateTime, setUpdateTime] = useState("Unknown");
    const [isLogFirstLoad, setIsLogFirstLoad] = useState(true);

    // API calls using custom hooks
    const {
        data: stat,
        loading: statLoading,
        error: statError,
        refetch: refetchStat
    } = useApi(`${API_ENDPOINT}/stat`, emptyStat, { interval: 58000 });

    const {
        data: wateringData,
        loading: wateringLoading,
        error: wateringError,
        refetch: refetchWatering
    } = useApi(`${API_ENDPOINT}/watering`, emptyWatering, { interval: 58000 });

    const {
        data: log,
        loading: logLoading,
        error: logError,
        refetch: refetchLog
    } = useApi(`${API_ENDPOINT}/proxy/json/api/log_view`, emptyLog, { retryInterval: 10000 });

    const {
        data: sysInfo,
        error: sysInfoError
    } = useApi(`${API_ENDPOINT}/sysinfo`, emptySysInfo, { interval: 58000 });

    const {
        data: actuatorSysInfo,
        error: actuatorSysInfoError
    } = useApi(`${API_ENDPOINT}/proxy/json/api/sysinfo`, emptySysInfo, { interval: 58000 });

    // EventSource for real-time updates
    useEventSource(`${API_ENDPOINT}/proxy/event/api/event`, {
        onMessage: (e) => {
            if (e.data === "log") {
                refetchLog();
                refetchStat();
                setUpdateTime(dayjs().format("llll"));
                setLogUpdateTrigger(prev => prev + 1);
            }
        }
    });

    // Update isLogFirstLoad when logLoading changes
    if (!logLoading && isLogFirstLoad) {
        setIsLogFirstLoad(false);
    }

    // Update time when stat data changes
    if (!statLoading && stat && updateTime === "Unknown") {
        setUpdateTime(dayjs().format("LLL"));
    }

    const hasError = statError || wateringError || logError || sysInfoError || actuatorSysInfoError;
    const isReady = !statLoading && !wateringLoading && !logLoading;

    const getErrorMessage = () => {
        if (statError) return `統計データ: ${statError}`;
        if (wateringError) return `散水データ: ${wateringError}`;
        if (logError) return `ログデータ: ${logError}`;
        if (sysInfoError) return `システム情報: ${sysInfoError}`;
        if (actuatorSysInfoError) return `アクチュエータ情報: ${actuatorSysInfoError}`;
        return "データの読み込みに失敗しました";
    };

    const handleRetry = useCallback(() => {
        refetchStat();
        refetchWatering();
        refetchLog();
    }, [refetchStat, refetchWatering, refetchLog]);

    // Format system info data with memoization
    // NOTE: バックエンド (my_lib.webapp.util) は値が取れないとき uptime に "?" を返すため、
    // 単純な truthy 判定では dayjs("?") → "Invalid Date" になる。dayjs().isValid() で弾く。
    const systemInfoMemo = useMemo(() => ({
        imageBuildDate: formatDateOrFallback(sysInfo?.image_build_date, "format"),
        imageBuildDateFrom: formatDateOrFallback(sysInfo?.image_build_date, "fromNow"),
        actuatorUptime: formatDateOrFallback(actuatorSysInfo?.uptime, "format"),
        actuatorUptimeFrom: formatDateOrFallback(actuatorSysInfo?.uptime, "fromNow"),
        actuatorLoadAverage: actuatorSysInfo?.load_average || "?"
    }), [sysInfo?.image_build_date, actuatorSysInfo?.uptime, actuatorSysInfo?.load_average]);

    const buildInfo = useMemo(() => ({
        buildDate: dayjs(import.meta.env.VITE_BUILD_DATE || new Date().toISOString()).format("LLL"),
        buildDateFrom: dayjs(import.meta.env.VITE_BUILD_DATE || new Date().toISOString()).fromNow()
    }), []);


    return (
        <>
            <div className="App">
                <div className="py-5 px-4 mb-4 bg-gradient-to-r from-blue-50 via-white to-blue-50 border-b border-blue-100 shadow-md">
                    <h1 className="text-2xl md:text-3xl font-bold my-0 text-center tracking-widest text-gray-800">
                        室外機自動冷却システム
                    </h1>
                </div>
                {hasError && (
                    <ErrorMessage
                        message={getErrorMessage()}
                        onRetry={handleRetry}
                    />
                )}
                <div className="mt-2">
                    <div className="container mx-auto px-4">
                        <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
                            <Watering isReady={isReady} watering={wateringData.watering} />
                            <History isReady={isReady} watering={wateringData.watering} />
                            <CoolingMode isReady={isReady} stat={stat} logUpdateTrigger={logUpdateTrigger} />
                            <AirConditioner isReady={isReady} stat={stat} />
                            <Sensor isReady={isReady} stat={stat} />
                            <Log isReady={!logLoading || !isLogFirstLoad} log={log} />
                        </div>
                    </div>
                </div>
                <div className="p-1 float-right text-right m-2 mt-4">
                    <small>
                        <p className="text-gray-500 m-0">
                            <small>更新日時: {updateTime}</small>
                        </p>
                        <p className="text-gray-500 m-0">
                            <small>
                                アクチュエータ起動時刻: {systemInfoMemo.actuatorUptime} [{systemInfoMemo.actuatorUptimeFrom}]
                            </small>
                        </p>
                        <p className="text-gray-500 m-0">
                            <small>
                                アクチュエータ load average: {systemInfoMemo.actuatorLoadAverage}
                            </small>
                        </p>
                        <p className="text-gray-500 m-0">
                            <small>
                                イメージビルド: {systemInfoMemo.imageBuildDate} [{systemInfoMemo.imageBuildDateFrom}]
                            </small>
                        </p>
                        <p className="text-gray-500 m-0">
                            <small>
                                React ビルド: {buildInfo.buildDate} [{buildInfo.buildDateFrom}]
                            </small>
                        </p>
                        <p className="text-gray-500 m-0">
                            <small>
                                React バージョン: {reactVersion}
                            </small>
                        </p>
                        <p className="text-3xl font-light mt-2">
                            <a
                                href={`${API_ENDPOINT}/proxy/html/api/metrics`}
                                className="text-gray-500 hover:text-gray-700 mr-3"
                            >
                                <ChartBarIcon className="size-7 inline" />
                            </a>
                            <a
                                href="https://github.com/kimata/unit-cooler"
                                className="text-gray-500 hover:text-gray-700"
                            >
                                <GitHubIcon className="size-7 inline" />
                            </a>
                        </p>
                    </small>
                </div>
            </div>
        </>
    );
}

export default App;
