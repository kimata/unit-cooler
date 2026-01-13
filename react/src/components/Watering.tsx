import React from "react";
import watering_icon from "../assets/watering.png";
import NumberFlow, { continuous } from '@number-flow/react';

import { ApiResponse } from "../lib/ApiResponse";
import { Loading } from "./common/Loading";
import { StatComponentProps } from "../types/common";

const Watering = React.memo(({ isReady, stat }: StatComponentProps) => {
    const amount = (watering: ApiResponse.Watering) => {
        return (
            <div className="card-body outdoor_unit">
                <div className="flex">
                    <div className="w-1/12">
                        <img src={watering_icon} alt="🚰" width="120px" />
                    </div>
                    <div className="w-11/12">
                        <div className="flex flex-col">
                            <div className="w-full">
                                <span
                                    className="text-left text-6xl font-light ml-4"
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
                                    className="text-left ml-4 text-gray-500"
                                    data-testid="watering-price-info"
                                >
                                    <NumberFlow
                                        value={watering.price}
                                        format={{ minimumFractionDigits: 1, maximumFractionDigits: 1 }}
                                        plugins={[continuous]}
                                        trend={1}
                                        className="font-bold text-3xl font-light digit"
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
        <div className="col-span-1">
            <div className="mb-3 text-center">
                <div className="card mb-4 shadow-sm">
                    <div className="card-header">
                        <h4 className="my-0 font-normal">本日の散水量</h4>
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
