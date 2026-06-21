import React, { useState, useEffect } from "react";
import type { Dayjs } from "dayjs";

import dayjs from "../lib/dayjs";
import type * as ApiResponse from "../lib/ApiResponse";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { DateDisplay } from "./common/DateDisplay";
import { EmptyValue } from "./common/EmptyValue";
import { FrequencyHeatBar } from "./common/FrequencyHeatBar";
import { Loading } from "./common/Loading";
import { ProgressBar } from "./common/ProgressBar";
import { Unit } from "./common/Unit";
import { BoltIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
    sensorGraph: ApiResponse.SensorGraph;
};

// 消費電力バー・頻度ヒートバーの軸の最大値（W）
const POWER_SCALE_W = 1500;

const AirConditioner = React.memo(({ isReady, stat, sensorGraph }: Props) => {
    type AirconRowProps = {
        airconData: ApiResponse.SensorData;
        graph?: ApiResponse.SensorGraphSeries | null;
    };
    const AirconRow: React.FC<AirconRowProps> = React.memo((props) => {
        const value = props.airconData.value;
        const hasValue = value != null;
        const currentValue = value ?? 0;
        const [previousValue, setPreviousValue] = useState(currentValue);
        const currentWidth = (100.0 * currentValue) / POWER_SCALE_W;
        const previousWidth = (100.0 * previousValue) / POWER_SCALE_W;

        useEffect(() => {
            setPreviousValue(currentValue);
        }, [currentValue]);

        const date: Dayjs | null = props.airconData.time != null ? dayjs(props.airconData.time) : null;

        return (
            <tr className="flex items-center">
                <td className="text-left w-[76px] whitespace-nowrap py-2 flex items-center h-10">{props.airconData.name}</td>
                <td className="flex-1 py-2 pr-3 flex items-center">
                    <div className="w-full">
                        <ProgressBar
                            fillPercent={currentWidth}
                            initialPercent={previousWidth}
                            durationSec={30.0}
                            ariaValueNow={currentValue}
                            ariaValueMax={POWER_SCALE_W}
                            // 過去12時間の電力頻度ヒートマップをトラック全面の背景に敷き、
                            // 半透明の塗りで分布を透かす（濃淡は zinc・地色は zinc-100）
                            trackClassName="bg-zinc-100"
                            fillClassName="bg-gray-500/80"
                            // 塗りの右端に細い濃色の縦線を重ね、現在値の位置を読み取りやすくする
                            fillCursorClassName="w-[0.75px] bg-gray-700"
                            trackBackground={
                                props.graph && props.graph.values.length > 0 ? (
                                    <FrequencyHeatBar
                                        values={props.graph.values}
                                        max={POWER_SCALE_W}
                                        className="absolute inset-0"
                                    />
                                ) : undefined
                            }
                        >
                            <b>
                                {hasValue ? (
                                    <AnimatedNumber value={value} decimals={0} useComma={true} />
                                ) : (
                                    <EmptyValue />
                                )}
                            </b>
                            <Unit>W</Unit>
                        </ProgressBar>
                    </div>
                </td>
                <td className="text-left w-[68px] py-2 pl-2 flex items-center h-10">
                    <DateDisplay date={date} format="relative" />
                </td>
                <td className="text-left w-[120px] whitespace-nowrap py-2 flex items-center h-10">
                    <DateDisplay date={date} format="absolute" />
                </td>
            </tr>
        );
    });
    AirconRow.displayName = "AirconRow";

    const coolerStatus = (stat: ApiResponse.Stat) => {
        if (stat.cooler_status.message) {
            return <div>{stat.cooler_status.message}</div>;
        }
    };

    const sensorInfo = (stat: ApiResponse.Stat) => {
        return (
            <div data-testid="aircon-info">
                <table className="w-full">
                    <thead>
                        <tr className="flex border-b border-gray-200">
                            <th className="w-[76px] text-left py-2 whitespace-nowrap">エアコン</th>
                            <th className="flex-1 text-left py-2 pr-3">値</th>
                            <th colSpan={2} className="w-[188px] text-left py-2 pl-2 whitespace-nowrap">
                                最新更新日時
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {(stat.sensor.power ?? []).map((airconData, index) => (
                            <AirconRow airconData={airconData} graph={sensorGraph.power?.[index]} key={index} />
                        ))}
                    </tbody>
                </table>
                <div className="text-left mt-4">{coolerStatus(stat)}</div>
            </div>
        );
    };

    return (
        <DashboardCard title="エアコン稼働状況" icon={<BoltIcon className="size-5 text-gray-500" />}>
            <CardBody>
                {isReady || (stat.sensor.power?.length ?? 0) > 0 ? sensorInfo(stat) : <Loading size="large" />}
            </CardBody>
        </DashboardCard>
    );
});

AirConditioner.displayName = "AirConditioner";

export { AirConditioner };
