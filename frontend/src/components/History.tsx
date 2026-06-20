import React, { useMemo } from "react";
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

    // 散水データからチャートデータを生成する。
    // watering は stat / log とは独立に到着するため、isReady を待たずに watering 単体で反映する
    // （isReady を待つと watering 到着済みでも log/stat ロード完了までゼロ表示のままになる）。
    // react-chartjs-2 が data prop の変更を内部で検知してチャートを更新するため、宣言的に渡す。
    const chartData = useMemo(() => {
        const hasData = (watering?.length ?? 0) >= 10;
        return {
            labels: Array.from(Array(10), (_, i) => (i == 9 ? "本日" : 9 - i + "日前")),
            datasets: [
                {
                    label: "散水量",
                    data: hasData
                        ? watering.map((w) => parseFloat(w["amount"].toFixed(1))).reverse()
                        : Array(10).fill(0),
                    backgroundColor: "rgba(128, 128, 128, 0.6)",
                },
            ],
        };
    }, [watering]);

    const history = () => (
        <CardBody>
            <div className="w-full relative h-[250px]" data-testid="history-info">
                <Bar options={chartOptions} data={chartData} />
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
