import React, { useState, useCallback } from "react";
import { motion, AnimatePresence, type Variants } from "framer-motion";

import dayjs from "../lib/dayjs";
import type * as ApiResponse from "../lib/ApiResponse";
import { CardBody } from "./common/Card";
import { DashboardCard } from "./common/DashboardCard";
import { Loading } from "./common/Loading";
import { Pagination } from "./common/Pagination";
import {
    AdjustmentsHorizontalIcon,
    ClipboardDocumentListIcon,
    DropletIcon,
    PauseCircleIcon,
    ToggleOffIcon,
    ToggleOnIcon,
    XCircleIcon,
} from "./icons";

type Props = {
    isReady: boolean;
    log: ApiResponse.Log;
};

// ページ遷移方向(custom=direction)に応じて入場・退場を対称に切り替える。
// 次へ(dir=1): 新項目は下から入り、旧項目は上へ抜ける。前へ(dir=-1)はその逆。
// height アニメ(0↔auto)は方向に依らない「展開」感が支配的で方向差が埋もれるため、
// opacity + 大きめの y スライドのみで方向を明確に表現する。
const logVariants: Variants = {
    enter: (dir: number) => ({ opacity: 0, y: dir * 56 }),
    center: { opacity: 1, y: 0 },
    exit: (dir: number) => ({ opacity: 0, y: dir * -56 }),
};

const Log = React.memo(({ isReady, log }: Props) => {
    const [page, setPage] = useState(1);
    // ページ遷移方向: 1 = ページ増加（次へ）, -1 = ページ減少（前へ）
    const [direction, setDirection] = useState(1);
    const size = 5;

    const handlePageChange = useCallback(
        (newPage: number) => {
            setDirection(newPage >= page ? 1 : -1);
            setPage(newPage);
        },
        [page],
    );

    const messageIcon = (message: string) => {
        if (message.match(/故障/)) {
            return (
                <span className="mr-2 text-red-500">
                    <XCircleIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/開始/)) {
            return (
                <span className="mr-2 text-sky-500">
                    <DropletIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/停止/)) {
            return (
                <span className="mr-2 text-gray-400">
                    <PauseCircleIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/ON Duty/)) {
            return (
                <span className="mr-2 text-green-500">
                    <ToggleOnIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/OFF Duty/)) {
            return (
                <span className="mr-2 text-gray-500">
                    <ToggleOffIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/変更/)) {
            return (
                <span className="mr-2 text-green-500">
                    <AdjustmentsHorizontalIcon className="size-5 inline" />
                </span>
            );
        }
    };

    const formatMessage = (message: string) => (
        <span>
            {messageIcon(message)}
            {message}
        </span>
    );

    const logData = (log: ApiResponse.LogEntry[]) => {
        if (log.length === 0) {
            return (
                <div>
                    <div className="text-left mb-3" data-testid="log">
                        <div className="flex">ログがありません．</div>
                    </div>
                </div>
            );
        }

        return (
            <div className="flex flex-col h-full">
                <div className="text-left flex-1 mb-4" data-testid="log">
                    <AnimatePresence initial={false} custom={direction} mode="popLayout">
                        {log.slice((page - 1) * size, page * size).map((entry, index) => {
                            // サーバーは tz 付き ISO 8601 を返す。ブラウザの TZ に依らず JST で表示する。
                            const date = dayjs(entry.date).tz("Asia/Tokyo");
                            const log_date = date.format("M月D日(ddd) HH:mm");
                            const log_fromNow = date.fromNow();
                            const isLast = index === Math.min(size, log.length - (page - 1) * size) - 1;

                            return (
                                <motion.div
                                    className="flex flex-col"
                                    key={entry.id}
                                    custom={direction}
                                    variants={logVariants}
                                    initial="enter"
                                    animate="center"
                                    exit="exit"
                                    transition={{ duration: 0.3, ease: "easeOut" }}
                                    layout
                                >
                                    <div className="w-full font-bold">
                                        {log_date}
                                        <small className="text-gray-500 ml-2">({log_fromNow})</small>
                                    </div>
                                    <div className="w-full mb-2">{formatMessage(entry.message)}</div>
                                    {!isLast && <hr className="border-t-2 border-dashed border-gray-300 my-3" />}
                                </motion.div>
                            );
                        })}
                    </AnimatePresence>
                </div>

                <div className="mt-auto pt-3 px-6 border-t border-gray-100">
                    <Pagination
                        page={page}
                        between={2}
                        total={log.length}
                        limit={size}
                        onChange={handlePageChange}
                    />
                </div>
            </div>
        );
    };

    return (
        <DashboardCard title="作動ログ" icon={<ClipboardDocumentListIcon className="size-5 text-gray-500" />}>
            <CardBody className="flex flex-col">
                {isReady ? logData(log.data) : <Loading size="large" />}
            </CardBody>
        </DashboardCard>
    );
});

Log.displayName = "Log";

export { Log };
