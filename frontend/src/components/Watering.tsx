import React from "react";

import watering_icon from "../assets/watering.png";
import type * as ApiResponse from "../lib/ApiResponse";
import { AnimatedNumber } from "./common/AnimatedNumber";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { Loading } from "./common/Loading";
import { Unit } from "./common/Unit";
import { DropletIcon } from "./icons";

type Props = {
    isReady: boolean;
    watering: ApiResponse.Watering[];
};

// 散水カードの背景画像 (室外機の壁)
const OUTDOOR_BG_CLASSES =
    "bg-[url('/wall.png')] bg-no-repeat bg-[length:200px] bg-[position:bottom_5px_right_5px]";

const Watering = React.memo(({ isReady, watering }: Props) => {
    const amount = (watering: ApiResponse.Watering) => (
        <CardBody>
            <div className={`flex items-center -m-4 p-4 ${OUTDOOR_BG_CLASSES}`}>
                <div className="shrink-0 w-[120px]">
                    <img src={watering_icon} alt="🚰" className="w-full h-auto" />
                </div>
                <div className="flex-1 ml-4 flex flex-col items-center">
                    <div className="w-full text-center">
                        <span className="text-6xl font-light" data-testid="watering-amount-info">
                            <AnimatedNumber value={watering.amount} decimals={1} className="font-bold digit" />
                            <Unit className="text-4xl">L</Unit>
                        </span>
                    </div>
                    <div className="w-full mt-3 text-center">
                        <span className="text-gray-500" data-testid="watering-price-info">
                            <AnimatedNumber value={watering.price} decimals={1} className="font-bold text-3xl digit" />
                            <Unit>円</Unit>
                        </span>
                    </div>
                </div>
            </div>
        </CardBody>
    );

    return (
        <DashboardCard title="本日の散水量" icon={<DropletIcon className="size-5 text-gray-500" />}>
            {isReady || (watering?.length ?? 0) > 0 ? (
                amount(watering?.[0] ?? { amount: 0, price: 0 })
            ) : (
                <CardBody>
                    <div className={`-m-4 p-4 ${OUTDOOR_BG_CLASSES}`}>
                        <Loading size="large" />
                    </div>
                </CardBody>
            )}
        </DashboardCard>
    );
});

Watering.displayName = "Watering";

export { Watering };
