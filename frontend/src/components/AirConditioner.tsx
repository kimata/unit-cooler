import React, { useState, useEffect } from "react";
import type { Dayjs } from "dayjs";

import dayjs from "../lib/dayjs";
import type * as ApiResponse from "../lib/ApiResponse";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { DateDisplay } from "./common/DateDisplay";
import { EmptyValue } from "./common/EmptyValue";
import { Loading } from "./common/Loading";
import { ProgressBar } from "./common/ProgressBar";
import { Unit } from "./common/Unit";
import { BoltIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
};

const AirConditioner = React.memo(({ isReady, stat }: Props) => {
    type AirconRowProps = { airconData: ApiResponse.SensorData };
    const AirconRow: React.FC<AirconRowProps> = React.memo((props) => {
        const value = props.airconData.value;
        const hasValue = value != null;
        const currentValue = value ?? 0;
        const [previousValue, setPreviousValue] = useState(currentValue);
        const currentWidth = (100.0 * currentValue) / 1500;
        const previousWidth = (100.0 * previousValue) / 1500;

        useEffect(() => {
            setPreviousValue(currentValue);
        }, [currentValue]);

        const date: Dayjs | null = props.airconData.time != null ? dayjs(props.airconData.time) : null;

        return (
            <tr className="flex items-center">
                <td className="text-left w-2/12 whitespace-nowrap py-2 flex items-center h-10">{props.airconData.name}</td>
                <td className="text-right w-5/12 py-2 pr-3 flex items-center">
                    <ProgressBar
                        fillPercent={currentWidth}
                        initialPercent={previousWidth}
                        durationSec={30.0}
                        ariaValueNow={currentValue}
                        ariaValueMax={1200}
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
                </td>
                <td className="text-left w-2/12 py-2 pl-2 flex items-center h-10">
                    <DateDisplay date={date} format="relative" />
                </td>
                <td className="text-left w-3/12 whitespace-nowrap py-2 flex items-center h-10">
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
                            <th className="w-2/12 text-left py-2">エアコン</th>
                            <th className="w-5/12 text-left py-2 pr-3">値</th>
                            <th colSpan={2} className="w-5/12 text-left py-2 pl-2">最新更新日時</th>
                        </tr>
                    </thead>
                    <tbody>
                        {(stat.sensor.power ?? []).map((airconData, index) => (
                            <AirconRow airconData={airconData} key={index} />
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
