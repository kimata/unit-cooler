import React from "react";
import "dayjs/locale/ja";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
dayjs.locale("ja");
dayjs.extend(relativeTime);

import reactStringReplace from "react-string-replace";

import { dateText } from "../lib/Util";
import type * as ApiResponse from "../lib/ApiResponse";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { Loading } from "./common/Loading";
import { ThermometerIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
};

const Sensor = React.memo(({ isReady, stat }: Props) => {
    const sensorRow = (label: string, sensorData: ApiResponse.SensorData, unit: React.JSX.Element) => {
        const value = sensorData.value;
        const hasValue = value != null;
        const hasTime = sensorData.time != null;
        const date = hasTime ? dayjs(sensorData.time) : null;

        // 照度・日射量の場合は値に応じて小数点桁数を調整
        const decimals = hasValue && ((label === "lux" && value >= 10) || (label === "solar_rad" && value >= 10)) ? 0 : 1;

        return (
            <tr className="flex" key={label}>
                <td className="text-left w-4/12 py-2" style={{overflow: 'visible', whiteSpace: 'nowrap'}}>{sensorData.name}</td>
                <td className="text-right w-3/12 py-2">
                    <div className="sensor-value" style={{whiteSpace: 'nowrap'}}>
                        <div className="sensor-number digit">
                            <b>
                                {hasValue ? (
                                    <AnimatedNumber
                                        value={value}
                                        decimals={decimals}
                                        useComma={label === "lux"}
                                    />
                                ) : (
                                    <span className="text-gray-400">—</span>
                                )}
                            </b>
                        </div>
                        <small className="sensor-unit whitespace-nowrap">{unit}</small>
                    </div>
                </td>
                <td className="text-left w-2/12 py-2 pl-2"><small>{date ? date.fromNow() : <span className="text-gray-400">—</span>}</small></td>
                <td className="text-left w-3/12 whitespace-nowrap py-2 pl-2">
                    <small>{date ? dateText(date) : <span className="text-gray-400">—</span>}</small>
                </td>
            </tr>
        );
    };

    const outdoorStatus = (stat: ApiResponse.Stat) => {
        if (stat.outdoor_status.message == null) {
            return;
        }

        let message = reactStringReplace(stat.outdoor_status.message, "m^2", () => (
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
                            <th className="w-3/12 text-left py-2">
                                値
                            </th>
                            <th colSpan={2} className="w-5/12 text-left py-2">
                                最新更新日時
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {stat.sensor.temp?.[0] && sensorRow("temp", stat.sensor.temp[0], <span>℃</span>)}
                        {stat.sensor.humi?.[0] && sensorRow("humi", stat.sensor.humi[0], <span>%</span>)}
                        {stat.sensor.lux?.[0] && sensorRow("lux", stat.sensor.lux[0], <span>lx</span>)}
                        {stat.sensor.solar_rad?.[0] && sensorRow(
                            "solar_rad",
                            stat.sensor.solar_rad[0],
                            <span>
                                W/m<sup>2</sup>
                            </span>
                        )}
                        {stat.sensor.rain?.[0] && sensorRow("rain", stat.sensor.rain[0], <span>mm/h</span>)}
                    </tbody>
                </table>
                <div className="text-left mt-4">{outdoorStatus(stat)}</div>
            </div>
        );
    };

    return (
        <div>
            <div className="text-center h-full">
                <div className="card shadow-sm h-full">
                    <div className="card-header">
                        <h4 className="my-0 font-normal">
                            <ThermometerIcon className="size-5 text-gray-500" />
                            センサー値
                        </h4>
                    </div>
                    <div className="card-body">{isReady || (stat.sensor.temp?.length ?? 0) > 0 ? sensorInfo(stat) : <Loading size="large" />}</div>
                </div>
            </div>
        </div>
    );
});

Sensor.displayName = 'Sensor';

export { Sensor };
