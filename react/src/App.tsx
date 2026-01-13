import { useState, useMemo, useCallback } from "react";
import "./App.css";

import { GitHubIcon, ChartBarIcon } from "./components/icons";

import "dayjs/locale/ja";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import localizedFormat from "dayjs/plugin/localizedFormat";

dayjs.locale("ja");
dayjs.extend(relativeTime);
dayjs.extend(localizedFormat);

import { version as reactVersion } from "react";

import { ApiResponse } from "./lib/ApiResponse";
import { useApi } from "./hooks/useApi";
import { useEventSource } from "./hooks/useEventSource";
import { ErrorMessage } from "./components/common/ErrorMessage";

import { Watering } from "./components/Watering";
import { History } from "./components/History";
import { CoolingMode } from "./components/CoolingMode";
import { AirConditioner } from "./components/AirConditioner";
import { Sensor } from "./components/Sensor";
import { Log } from "./components/Log";

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
        data: log,
        loading: logLoading,
        error: logError,
        refetch: refetchLog
    } = useApi(`${API_ENDPOINT}/proxy/json/api/log_view`, emptyLog);

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

    const hasError = statError || logError || sysInfoError || actuatorSysInfoError;
    const isReady = !statLoading && !logLoading;

    const getErrorMessage = () => {
        if (statError) return `統計データ: ${statError}`;
        if (logError) return `ログデータ: ${logError}`;
        if (sysInfoError) return `システム情報: ${sysInfoError}`;
        if (actuatorSysInfoError) return `アクチュエータ情報: ${actuatorSysInfoError}`;
        return "データの読み込みに失敗しました";
    };

    const handleRetry = useCallback(() => {
        refetchStat();
        refetchLog();
    }, [refetchStat, refetchLog]);

    // Format system info data with memoization
    const systemInfoMemo = useMemo(() => ({
        imageBuildDate: sysInfo?.image_build_date ? dayjs(sysInfo.image_build_date).format("LLL") : "?",
        imageBuildDateFrom: sysInfo?.image_build_date ? dayjs(sysInfo.image_build_date).fromNow() : "?",
        actuatorUptime: actuatorSysInfo?.uptime ? dayjs(actuatorSysInfo.uptime).format("LLL") : "?",
        actuatorUptimeFrom: actuatorSysInfo?.uptime ? dayjs(actuatorSysInfo.uptime).fromNow() : "?",
        actuatorLoadAverage: actuatorSysInfo?.load_average || "?"
    }), [sysInfo?.image_build_date, actuatorSysInfo?.uptime, actuatorSysInfo?.load_average]);

    const buildInfo = useMemo(() => ({
        buildDate: dayjs(import.meta.env.VITE_BUILD_DATE || new Date().toISOString()).format("LLL"),
        buildDateFrom: dayjs(import.meta.env.VITE_BUILD_DATE || new Date().toISOString()).fromNow()
    }), []);


    return (
        <>
            <div className="App">
                <div className="py-4 px-4 mb-4 bg-gradient-to-r from-gray-50 via-white to-gray-50 border-b shadow-sm">
                    <h1 className="text-2xl md:text-3xl font-light my-0 text-center tracking-widest text-gray-700">
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
                            <Watering isReady={isReady} stat={stat} />
                            <History isReady={isReady} stat={stat} />
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
