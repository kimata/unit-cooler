import React, { useState, useEffect } from "react";

import type * as ApiResponse from "../lib/ApiResponse";
import { CONTROLLER_STALE_SEC } from "../hooks/useDashboardData";

type Props = {
    // stat 等の初回取得が完了しているか
    isReady: boolean;
    // stat API の取得エラー（連続失敗中は非 null が維持される）
    statError: string | null;
    // SSE の接続状態（null = 接続確立前）
    sseConnected: boolean | null;
    // stat.freshness（バックエンド更新前のレスポンスでは欠落しうる）
    freshness: ApiResponse.Freshness | undefined;
    // Actuator の状態を受信できているか（stat.actuator_status != null）
    actuatorAlive: boolean;
    // stat の最終取得成功時刻（ms）。未取得は null
    lastUpdateMs: number | null;
};

type Issue = {
    level: "error" | "warn";
    label: string;
    detail: string;
};

// 経過秒を「N 秒前 / N 分前 / N 時間前」に整形する
function formatAgo(sec: number): string {
    const s = Math.max(0, Math.floor(sec));
    if (s < 60) {
        return `${s} 秒前`;
    }
    if (s < 3600) {
        return `${Math.floor(s / 60)} 分前`;
    }
    return `${Math.floor(s / 3600)} 時間前`;
}

// ヘッダー直下の接続状態・データ鮮度インジケータ。
// 「サーバーは応答しているが Controller / Actuator からのデータが止まっている」
// といった静かな障害を可視化する。
const ConnectionStatus = React.memo(
    ({ isReady, statError, sseConnected, freshness, actuatorAlive, lastUpdateMs }: Props) => {
        // 「最終更新 N 秒前」と鮮度判定を進めるための現在時刻（1 秒ごとに更新）
        const [nowMs, setNowMs] = useState(() => Date.now());
        useEffect(() => {
            const timer = setInterval(() => setNowMs(Date.now()), 1000);
            return () => clearInterval(timer);
        }, []);

        const elapsedSec = lastUpdateMs != null ? (nowMs - lastUpdateMs) / 1000 : null;

        const issues: Issue[] = [];

        if (statError != null) {
            issues.push({
                level: "error",
                label: "サーバー接続エラー",
                detail: `サーバーからの統計データ取得に失敗しています（${statError}）`,
            });
        }

        if (isReady) {
            // freshness はレスポンス時点の経過秒なので、取得からの経過分を加算して評価する
            const controllerSec =
                freshness?.controller_sec == null ? null : freshness.controller_sec + (elapsedSec ?? 0);
            if (controllerSec == null) {
                issues.push({
                    level: "error",
                    label: "Controller 途絶",
                    detail: "Controller から制御メッセージを受信できていません",
                });
            } else if (controllerSec > CONTROLLER_STALE_SEC) {
                issues.push({
                    level: "error",
                    label: "Controller 途絶",
                    detail: `Controller からの最終受信は ${formatAgo(controllerSec)} です`,
                });
            }

            if (!actuatorAlive) {
                issues.push({
                    level: "error",
                    label: "Actuator 途絶",
                    detail: "Actuator の状態を 60 秒以上受信できていません",
                });
            }
        }

        if (sseConnected === false) {
            issues.push({
                level: "warn",
                label: "イベント接続断",
                detail: "サーバーからのイベント通知（SSE）が切断されています。再接続中です",
            });
        }

        const hasErrorIssue = issues.some((issue) => issue.level === "error");
        const dotClass =
            issues.length === 0
                ? isReady
                    ? "bg-green-500"
                    : "bg-gray-300 animate-pulse"
                : hasErrorIssue
                  ? "bg-red-500"
                  : "bg-yellow-400";
        const textClass =
            issues.length === 0 ? "text-gray-400" : hasErrorIssue ? "text-red-600" : "text-yellow-600";
        const label =
            issues.length === 0
                ? isReady
                    ? "接続正常"
                    : "接続中..."
                : issues.map((issue) => issue.label).join(" / ");
        const detail = issues.length > 0 ? issues.map((issue) => issue.detail).join("\n") : undefined;

        return (
            <div
                className="flex items-center justify-end gap-2 text-sm px-1 mb-2"
                data-testid="connection-status"
            >
                <span className={`inline-block size-2.5 rounded-full ${dotClass}`} aria-hidden="true" />
                <span className={`${textClass} ${detail ? "cursor-help" : ""}`} title={detail}>
                    {label}
                </span>
                {elapsedSec != null && (
                    <span className="text-gray-400">最終更新 {formatAgo(elapsedSec)}</span>
                )}
            </div>
        );
    }
);

ConnectionStatus.displayName = "ConnectionStatus";

export { ConnectionStatus };
