import React from "react";
import reactStringReplace from "react-string-replace";
import type { Dayjs } from "dayjs";

import dayjs from "../lib/dayjs";
import type * as ApiResponse from "../lib/ApiResponse";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { Card, CardBody, CardHeader } from "./common/Card";
import { DateDisplay } from "./common/DateDisplay";
import { EmptyValue } from "./common/EmptyValue";
import { Loading } from "./common/Loading";
import { Unit } from "./common/Unit";
import { ThermometerIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
};

const Sensor = React.memo(({ isReady, stat }: Props) => {
    const sensorRow = (label: string, sensorData: ApiResponse.SensorData, unit: React.JSX.Element) => {
        const value = sensorData.value;
        const hasValue = value != null;
        const date: Dayjs | null = sensorData.time != null ? dayjs(sensorData.time) : null;

        // 照度・日射量の場合は値に応じて小数点桁数を調整
        const decimals = hasValue && ((label === "lux" && value >= 10) || (label === "solar_rad" && value >= 10)) ? 0 : 1;

        return (
            <tr className="flex" key={label}>
                <td className="text-left w-4/12 py-2 whitespace-nowrap overflow-visible">{sensorData.name}</td>
                <td className="text-right w-3/12 py-2">
                    <div className="inline-flex justify-end items-baseline w-full whitespace-nowrap">
                        <div className="digit text-right text-xl min-w-[4.5em]">
                            <b>
                                {hasValue ? (
                                    <AnimatedNumber value={value} decimals={decimals} useComma={label === "lux"} />
                                ) : (
                                    <EmptyValue />
                                )}
                            </b>
                        </div>
                        <Unit>{unit}</Unit>
                    </div>
                </td>
                <td className="text-left w-2/12 py-2 pl-2">
                    <DateDisplay date={date} format="relative" />
                </td>
                <td className="text-left w-3/12 whitespace-nowrap py-2 pl-2">
                    <DateDisplay date={date} format="absolute" />
                </td>
            </tr>
        );
    };

    const outdoorStatus = (stat: ApiResponse.Stat) => {
        if (stat.outdoor_status.message == null) {
            return;
        }

        const message = reactStringReplace(stat.outdoor_status.message, "m^2", () => (
            <span>
                m<sup>2</sup>
            </span>
        ));

        return <div>{message}</div>;
    };

    const sensorInfo = (stat: ApiResponse.Stat) => {
        return (
            <div data-testid="sensor-info">
                <table className="w-full">
                    <thead>
                        <tr className="flex border-b border-gray-200">
                            <th className="w-4/12 text-left py-2">センサー</th>
                            <th className="w-3/12 text-left py-2">値</th>
                            <th colSpan={2} className="w-5/12 text-left py-2">最新更新日時</th>
                        </tr>
                    </thead>
                    <tbody>
                        {stat.sensor.temp?.[0] && sensorRow("temp", stat.sensor.temp[0], <span>℃</span>)}
                        {stat.sensor.humi?.[0] && sensorRow("humi", stat.sensor.humi[0], <span>%</span>)}
                        {stat.sensor.lux?.[0] && sensorRow("lux", stat.sensor.lux[0], <span>lx</span>)}
                        {stat.sensor.solar_rad?.[0] && sensorRow(
                            "solar_rad",
                            stat.sensor.solar_rad[0],
                            <span>W/m<sup>2</sup></span>
                        )}
                        {stat.sensor.rain?.[0] && sensorRow("rain", stat.sensor.rain[0], <span>mm/h</span>)}
                    </tbody>
                </table>
                <div className="text-left mt-4">{outdoorStatus(stat)}</div>
            </div>
        );
    };

    return (
        <div className="flex flex-col h-full">
            <div className="flex-1 flex flex-col text-center">
                <Card>
                    <CardHeader>
                        <ThermometerIcon className="size-5 text-gray-500" />
                        センサー値
                    </CardHeader>
                    <CardBody>
                        {isReady || (stat.sensor.temp?.length ?? 0) > 0 ? sensorInfo(stat) : <Loading size="large" />}
                    </CardBody>
                </Card>
            </div>
        </div>
    );
});

Sensor.displayName = "Sensor";

export { Sensor };
