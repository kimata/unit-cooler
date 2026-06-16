import React, { useMemo, useRef, useEffect } from "react";
import { Chart, CategoryScale, LinearScale, BarElement, Tooltip } from "chart.js";
import type { ChartOptions, TooltipItem } from "chart.js";
import { Bar } from "react-chartjs-2";

Chart.register(CategoryScale, LinearScale, BarElement, Tooltip);

import type * as ApiResponse from "../lib/ApiResponse";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { Loading } from "./common/Loading";
import { CalendarDaysIcon } from "./icons";

type Props = {
    isReady: boolean;
    watering: ApiResponse.Watering[];
};

const History = React.memo(({ isReady, watering }: Props) => {
    const chartRef = useRef<Chart<"bar"> | null>(null);

    // chartOptionsは変更されないのでメモ化
    const chartOptions: ChartOptions<"bar"> = useMemo(
        () => ({
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            scales: {
                y: {
                    ticks: { callback: (value: string | number) => value + " L" },
                    title: { text: "散水量", display: true },
                },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (context: TooltipItem<"bar">) =>
                            context.dataset.label + ": " + context.parsed.y + " L",
                    },
                },
            },
        }),
        []
    );

    // 初期データ
    const initialChartData = useMemo(
        () => ({
            labels: Array.from(Array(10), (_, i) => (i == 9 ? "本日" : 9 - i + "日前")),
            datasets: [
                {
                    label: "散水量",
                    data: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                    backgroundColor: "rgba(128, 128, 128, 0.6)",
                },
            ],
        }),
        []
    );

    // データが更新された時にチャートを更新
    useEffect(() => {
        if (chartRef.current && isReady && watering && (watering?.length ?? 0) >= 10) {
            const chart = chartRef.current;
            const newData = watering.map((w) => parseFloat(w["amount"].toFixed(1))).reverse();
            chart.data.datasets[0].data = newData;
            chart.update("none");
        }
    }, [isReady, watering]);

    const history = () => (
        <CardBody>
            <div className="w-full relative h-[250px]" data-testid="history-info">
                <Bar ref={chartRef} options={chartOptions} data={initialChartData} />
            </div>
        </CardBody>
    );

    return (
        <DashboardCard title="散水履歴" icon={<CalendarDaysIcon className="size-5 text-gray-500" />}>
            {isReady || (watering?.length ?? 0) > 0 ? history() : (
                <CardBody>
                    <Loading size="large" />
                </CardBody>
            )}
        </DashboardCard>
    );
});

History.displayName = "History";

export { History };
