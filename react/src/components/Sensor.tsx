import React from "react";
import "dayjs/locale/ja";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
dayjs.locale("ja");
dayjs.extend(relativeTime);

import reactStringReplace from "react-string-replace";

import { dateText } from "../lib/Util";
import { ApiResponse } from "../lib/ApiResponse";
import { AnimatedNumber } from "./common/AnimatedNumber";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
};

const Sensor = React.memo(({ isReady, stat }: Props) => {
    const loading = () => {
        return (
            <span className="text-6xl font-light align-middle ml-4">
                <span className="text-4xl font-light">Loading...</span>
            </span>
        );
    };

    const sensorRow = (label: string, sensorData: ApiResponse.SensorData, unit: React.JSX.Element) => {
        let date = dayjs(sensorData.time);

        // 照度・日射量の場合は値に応じて小数点桁数を調整
        const decimals = (label === "lux" && sensorData.value >= 10) || (label === "solar_rad" && sensorData.value >= 10) ? 0 : 1;

        return (
            <tr className="flex" key={label}>
                <td className="text-left w-4/12 py-2" style={{overflow: 'visible', whiteSpace: 'nowrap'}}>{sensorData.name}</td>
                <td className="text-right w-3/12 py-2">
                    <div className="sensor-value" style={{whiteSpace: 'nowrap'}}>
                        <div className="sensor-number digit">
                            <b>
                                <AnimatedNumber
                                    value={sensorData.value || 0}
                                    decimals={decimals}
                                    useComma={label === "lux"}
                                />
                            </b>
                        </div>
                        <div className="sensor-unit" style={{whiteSpace: 'nowrap'}}>
                            <small>{unit}</small>
                        </div>
                    </div>
                </td>
                <td className="text-right w-2/12 py-2">{date.fromNow()}</td>
                <td className="text-left w-3/12 whitespace-nowrap py-2">
                    <small>{dateText(date)}</small>
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
                        {sensorRow("temp", stat.sensor.temp[0], <span>℃</span>)}
                        {sensorRow("humi", stat.sensor.humi[0], <span>%</span>)}
                        {sensorRow("lux", stat.sensor.lux[0], <span>lx</span>)}
                        {sensorRow(
                            "solar_rad",
                            stat.sensor.solar_rad[0],
                            <span>
                                W/m<sup>2</sup>
                            </span>
                        )}
                        {sensorRow("rain", stat.sensor.rain[0], <span>mm/h</span>)}
                    </tbody>
                </table>
                <div className="text-left">{outdoorStatus(stat)}</div>
            </div>
        );
    };

    return (
        <div className="col-span-1">
            <div className="mb-3 text-center">
                <div className="card mb-4 shadow-sm">
                    <div className="card-header">
                        <h4 className="my-0 font-normal">センサー値</h4>
                    </div>
                    <div className="card-body">{isReady || stat.sensor.temp.length > 0 ? sensorInfo(stat) : loading()}</div>
                </div>
            </div>
        </div>
    );
});

Sensor.displayName = 'Sensor';

export { Sensor };
