import React, { useMemo } from "react";
import { version as reactVersion } from "react";

import { formatDateOrFallback } from "../lib/datetime";
import type * as ApiResponse from "../lib/ApiResponse";
import { GitHubIcon, ChartBarIcon } from "./icons";

type Props = {
    apiEndpoint: string;
    updateTime: string;
    sysInfo: ApiResponse.SysInfo;
    actuatorSysInfo: ApiResponse.SysInfo;
};

// ダッシュボード下部のシステム情報・ビルド情報・外部リンク
const Footer = React.memo(({ apiEndpoint, updateTime, sysInfo, actuatorSysInfo }: Props) => {
    const systemInfo = useMemo(
        () => ({
            imageBuildDate: formatDateOrFallback(sysInfo?.image_build_date, "format"),
            imageBuildDateFrom: formatDateOrFallback(sysInfo?.image_build_date, "fromNow"),
            actuatorUptime: formatDateOrFallback(actuatorSysInfo?.uptime, "format"),
            actuatorUptimeFrom: formatDateOrFallback(actuatorSysInfo?.uptime, "fromNow"),
            actuatorLoadAverage: actuatorSysInfo?.load_average || "?",
        }),
        [sysInfo?.image_build_date, actuatorSysInfo?.uptime, actuatorSysInfo?.load_average]
    );

    const buildInfo = useMemo(() => {
        const buildDate = import.meta.env.VITE_BUILD_DATE || new Date().toISOString();
        return {
            buildDate: formatDateOrFallback(buildDate, "format"),
            buildDateFrom: formatDateOrFallback(buildDate, "fromNow"),
        };
    }, []);

    return (
        <div className="p-1 float-right text-right m-2 mt-4">
            <small>
                <p className="text-gray-500 m-0">
                    <small>更新日時: {updateTime}</small>
                </p>
                <p className="text-gray-500 m-0">
                    <small>
                        アクチュエータ起動時刻: {systemInfo.actuatorUptime} [{systemInfo.actuatorUptimeFrom}]
                    </small>
                </p>
                <p className="text-gray-500 m-0">
                    <small>アクチュエータ load average: {systemInfo.actuatorLoadAverage}</small>
                </p>
                <p className="text-gray-500 m-0">
                    <small>
                        イメージビルド: {systemInfo.imageBuildDate} [{systemInfo.imageBuildDateFrom}]
                    </small>
                </p>
                <p className="text-gray-500 m-0">
                    <small>
                        React ビルド: {buildInfo.buildDate} [{buildInfo.buildDateFrom}]
                    </small>
                </p>
                <p className="text-gray-500 m-0">
                    <small>React バージョン: {reactVersion}</small>
                </p>
                <p className="text-3xl font-light mt-2">
                    <a
                        href={`${apiEndpoint}/proxy/html/api/metrics`}
                        className="text-gray-500 hover:text-gray-700 mr-3"
                    >
                        <ChartBarIcon className="size-7 inline" />
                    </a>
                    <a href="https://github.com/kimata/unit-cooler" className="text-gray-500 hover:text-gray-700">
                        <GitHubIcon className="size-7 inline" />
                    </a>
                </p>
            </small>
        </div>
    );
});

Footer.displayName = "Footer";

export { Footer };
