import React from "react";
import watering_icon from "../assets/watering.png";
import NumberFlow, { continuous } from '@number-flow/react';

import { ApiResponse } from "../lib/ApiResponse";
import { Loading } from "./common/Loading";
import { StatComponentProps } from "../types/common";
import { DropletIcon } from "./icons";

const Watering = React.memo(({ isReady, stat }: StatComponentProps) => {
    const amount = (watering: ApiResponse.Watering) => {
        return (
            <div className="card-body outdoor_unit">
                <div className="flex items-center">
                    <div className="shrink-0" style={{ width: '120px' }}>
                        <img src={watering_icon} alt="🚰" className="w-full h-auto" />
                    </div>
                    <div className="flex-1 ml-4">
                        <div className="flex flex-col">
                            <div className="w-full">
                                <span
                                    className="text-left text-6xl font-light"
                                    data-testid="watering-amount-info"
                                >
                                    <NumberFlow
                                        value={watering.amount}
                                        format={{ minimumFractionDigits: 1, maximumFractionDigits: 1 }}
                                        plugins={[continuous]}
                                        trend={1}
                                        className="font-bold digit"
                                    />
                                    <span className="text-4xl font-light ml-2">L</span>
                                </span>
                            </div>
                            <div className="w-full mt-3">
                                <span
                                    className="text-left text-gray-500"
                                    data-testid="watering-price-info"
                                >
                                    <NumberFlow
                                        value={watering.price}
                                        format={{ minimumFractionDigits: 1, maximumFractionDigits: 1 }}
                                        plugins={[continuous]}
                                        trend={1}
                                        className="font-bold text-3xl digit"
                                    />
                                    <span className="ml-2">円</span>
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div>
            <div className="text-center h-full">
                <div className="card shadow-sm h-full">
                    <div className="card-header">
                        <h4 className="my-0 font-normal">
                            <DropletIcon className="size-5 text-blue-500" />
                            本日の散水量
                        </h4>
                    </div>
                    {isReady || stat.watering.length > 0 ? amount(stat.watering[0]) : (
                        <div className="card-body outdoor_unit">
                            <Loading size="large" />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
});

Watering.displayName = 'Watering';

export { Watering };
