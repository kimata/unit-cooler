import React, { useState, useEffect } from "react";
import "dayjs/locale/ja";
import dayjs, { locale, extend } from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
locale("ja");
extend(relativeTime);

import { motion } from "framer-motion";
import { dateText } from "../lib/Util";
import { ApiResponse } from "../lib/ApiResponse";
import { Loading } from "./common/Loading";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { BoltIcon } from "./icons";

type Props = {
    isReady: boolean;
    stat: ApiResponse.Stat;
};

const AirConditioner = React.memo(({ isReady, stat }: Props) => {

    const valueInt = (value: number | null) => {
        if (value == null) {
            return 0;
        }

        if (typeof value === "string") {
            return parseInt(value);
        } else {
            return value;
        }
    };

    type AirconRowProps = { airconData: ApiResponse.SensorData };
    const AirconRow: React.FC<AirconRowProps> = React.memo((props) => {
        const [previousValue, setPreviousValue] = useState(props.airconData.value || 0);
        const currentWidth = (100.0 * props.airconData.value) / 1500;
        const previousWidth = (100.0 * previousValue) / 1500;

        useEffect(() => {
            setPreviousValue(props.airconData.value || 0);
        }, [props.airconData.value]);

        let date = dayjs(props.airconData.time);

        return (
            <tr key="{index}" className="flex">
                <td className="text-left w-2/12 whitespace-nowrap py-2">{props.airconData.name}</td>
                <td className="text-right w-5/12 py-2 pr-3">
                    <div className="progress-label-container">
                        <div className="progress" style={{ height: "2em" }}>
                            <motion.div
                                className="progress-bar bg-gray-500"
                                role="progressbar"
                                aria-valuenow={valueInt(props.airconData.value)}
                                aria-valuemin={0}
                                aria-valuemax={1200}
                                initial={{ width: previousWidth + "%" }}
                                animate={{ width: currentWidth + "%" }}
                                transition={{ duration: 30.0, ease: "easeOut" }}
                            ></motion.div>
                        </div>
                        <div className="progress-label digit">
                            <b>
                                <AnimatedNumber
                                    value={props.airconData.value || 0}
                                    decimals={0}
                                    useComma={true}
                                />
                            </b>
                            <small className="ml-2">W</small>
                        </div>
                    </div>
                </td>
                <td className="text-left w-2/12 py-2 pl-2">{date.fromNow()}</td>
                <td className="text-left w-3/12 whitespace-nowrap py-2">
                    <small>{dateText(date)}</small>
                </td>
            </tr>
        );
    });
    const coolerStatus = (stat: ApiResponse.Stat) => {
        if (stat.cooler_status.message != null) {
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
                            <th colSpan={2} className="w-5/12 text-left py-2 pl-2">
                                最新更新日時
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {stat.sensor.power.map((airconData: ApiResponse.SensorData, index: number) => (
                            <AirconRow airconData={airconData} key={index} />
                        ))}
                    </tbody>
                </table>
                <div className="text-left mt-4">{coolerStatus(stat)}</div>
            </div>
        );
    };

    return (
        <div>
            <div className="text-center h-full">
                <div className="card shadow-sm h-full">
                    <div className="card-header">
                        <h4 className="my-0 font-normal">
                            <BoltIcon className="size-5 text-gray-500" />
                            エアコン稼働状況
                        </h4>
                    </div>
                    <div className="card-body">{isReady || stat.sensor.power.length > 0 ? sensorInfo(stat) : <Loading size="large" />}</div>
                </div>
            </div>
        </div>
    );
});

AirConditioner.displayName = 'AirConditioner';

export { AirConditioner };
