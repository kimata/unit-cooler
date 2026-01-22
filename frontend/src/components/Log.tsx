import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Pagination } from "./common/Pagination";
import { XCircleIcon, SunIcon, AdjustmentsHorizontalIcon, ToggleOnIcon, ToggleOffIcon, ClipboardDocumentListIcon } from "./icons";

import "dayjs/locale/ja";
import dayjs, { locale, extend } from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
locale("ja");
extend(relativeTime);

import type * as ApiResponse from "../lib/ApiResponse";

type Props = {
    isReady: boolean;
    log: ApiResponse.Log;
};

const Log = React.memo(({ isReady, log }: Props) => {
    const [page, setPage] = useState(1);
    const size = 5;

    const handlePageChange = useCallback((page: number) => {
        setPage(page);
    }, []);

    const loading = () => {
        return (
            <span className="text-6xl font-light align-middle ml-4">
                <span className="text-4xl font-light">Loading...</span>
            </span>
        );
    };

    const messageIcon = (message: string) => {
        if (message.match(/故障/)) {
            return (
                <span className="mr-2 text-red-500">
                    <XCircleIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/開始/)) {
            return (
                <span className="mr-2 text-red-500">
                    <SunIcon className="size-5 inline" />
                </span>
            );
        } else if (message.match(/停止/)) {
            return (
                <span className="mr-2 text-yellow-500">
                    <SunIcon className="size-5 inline" />
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

    const formatMessage = (message: string) => {
        return (
            <span>
                {messageIcon(message)}
                {message}
            </span>
        );
    };

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
                    <AnimatePresence initial={false}>
                        {log.slice((page - 1) * size, page * size).map((entry: ApiResponse.LogEntry, index: number) => {
                            let date = dayjs(entry.date);
                            let log_date = date.format("M月D日(ddd) HH:mm");
                            let log_fromNow = date.fromNow();
                            const isLast = index === Math.min(size, log.length - (page - 1) * size) - 1;

                            return (
                                <motion.div
                                    className="flex flex-col"
                                    key={entry.id}
                                    initial={{ opacity: 0, height: 0, y: -20 }}
                                    animate={{ opacity: 1, height: "auto", y: 0 }}
                                    exit={{ opacity: 0, height: 0, y: -20 }}
                                    transition={{
                                        duration: 0.3,
                                        ease: "easeOut"
                                    }}
                                    layout
                                >
                                    <div className="w-full font-bold">
                                        {log_date}
                                        <small className="text-gray-500 ml-2">({log_fromNow})</small>
                                    </div>
                                    <div className="w-full log-message mb-2">{formatMessage(entry.message)}</div>
                                    {!isLast && <hr className="dashed-hr" />}
                                </motion.div>
                            );
                        })}
                    </AnimatePresence>
                </div>

                <div className="mt-auto pt-3 border-t border-gray-100">
                    <Pagination
                        page={page}
                        between={3}
                        total={log.length}
                        limit={size}
                        onChange={handlePageChange}
                    />
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
                            <ClipboardDocumentListIcon className="size-5 text-gray-500" />
                            作動ログ
                        </h4>
                    </div>
                    <div className="card-body flex flex-col">{isReady ? logData(log.data) : loading()}</div>
                </div>
            </div>
        </div>
    );
});

Log.displayName = 'Log';

export { Log };
