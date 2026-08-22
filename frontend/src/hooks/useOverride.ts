import { useState, useEffect, useCallback } from "react";

import { API_ENDPOINT } from "../lib/api";
import type * as ApiResponse from "../lib/ApiResponse";
import { useApi } from "./useApi";

// 停止・再開ボタン押下後、Actuator の実効状態 (stat.actuator_status.override_active) が
// 追いつくまでの遷移状態。UI はこの間「処理中」表示を出す。
export type OverridePending = "stop" | "resume" | null;

// 実効状態の確認ポーリング間隔と、確認できない場合に遷移状態を諦めるまでの時間
const CONFIRM_POLL_MS = 1000;
const CONFIRM_TIMEOUT_MS = 20000;

const emptyOverride: ApiResponse.OverrideStatus = { enabled: false, until: null };

// 散水の手動オーバーライド（強制 OFF）の状態と操作を提供するフック。
//
// POST 直後は override API の状態（=指示）と Actuator の実効状態（=結果）が
// 一時的に食い違うため、pending で遷移中であることを表し、実効状態が追いつく
// まで stat を短周期で再取得する。
export function useOverride(actuatorOverrideActive: boolean | null, refetchStat: () => Promise<void>) {
    const {
        data: override,
        loading,
        refetch,
    } = useApi<ApiResponse.OverrideStatus>(`${API_ENDPOINT}/proxy/json/api/override`, emptyOverride, {
        // stat と同程度の間隔でポーリングし、他クライアントからの変更も反映する
        interval: 58000,
    });
    const [pending, setPending] = useState<OverridePending>(null);
    const [postError, setPostError] = useState<string | null>(null);

    // 遷移中は実効状態が追いつくまで stat を短周期で再取得する
    useEffect(() => {
        if (pending == null) {
            return;
        }

        if (actuatorOverrideActive === (pending === "stop")) {
            setPending(null);
            return;
        }

        const pollTimer = setInterval(() => {
            refetchStat();
        }, CONFIRM_POLL_MS);
        // Actuator 途絶等で実効状態を確認できない場合は諦めて通常表示に戻す
        const giveUpTimer = setTimeout(() => setPending(null), CONFIRM_TIMEOUT_MS);
        return () => {
            clearInterval(pollTimer);
            clearTimeout(giveUpTimer);
        };
    }, [pending, actuatorOverrideActive, refetchStat]);

    const post = useCallback(
        async (url: string, body: object | undefined, action: "stop" | "resume") => {
            setPostError(null);
            setPending(action);
            try {
                const response = await fetch(url, {
                    method: "POST",
                    ...(body != null && {
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(body),
                    }),
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                await response.json();
                await refetch();
            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : "通信に失敗しました";
                setPostError(errorMessage);
                setPending(null);
                console.error("Override API error:", err);
            }
        },
        [refetch]
    );

    const pause = useCallback(
        (minutes: number) =>
            post(`${API_ENDPOINT}/proxy/json/api/override`, { duration_min: minutes }, "stop"),
        [post]
    );

    const resume = useCallback(
        () => post(`${API_ENDPOINT}/proxy/json/api/override/clear`, undefined, "resume"),
        [post]
    );

    return { override, loading, pending, postError, pause, resume };
}
