import React, { useState, useEffect, useCallback } from "react";

import { API_ENDPOINT } from "../lib/api";
import { ExclamationTriangleIcon } from "./icons";

type Props = {
    // ハザード解除成功後に呼ばれる（stat の再取得などに使う）
    onCleared: () => void;
};

// 確認状態（「本当に解除しますか？」）を自動で戻すまでの時間（ミリ秒）
const CONFIRM_TIMEOUT_MS = 10000;

// ハザード（漏水・電磁弁故障）検知時に画面上部へ表示する警告バナー。
// 解除は誤操作防止のため 2 段階（解除 → 解除する）にしている。
const HazardBanner = React.memo(({ onCleared }: Props) => {
    const [confirming, setConfirming] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 確認状態のまま放置された場合は自動で元に戻す
    useEffect(() => {
        if (!confirming) {
            return;
        }
        const timer = setTimeout(() => setConfirming(false), CONFIRM_TIMEOUT_MS);
        return () => clearTimeout(timer);
    }, [confirming]);

    const handleClear = useCallback(async () => {
        setSubmitting(true);
        setError(null);
        try {
            const response = await fetch(`${API_ENDPOINT}/proxy/json/api/hazard/clear`, {
                method: "POST",
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            await response.json();
            setConfirming(false);
            onCleared();
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : "通信に失敗しました";
            setError(errorMessage);
            console.error("Hazard clear error:", err);
        } finally {
            setSubmitting(false);
        }
    }, [onCleared]);

    const buttonBase = "px-2 py-1 text-sm rounded transition-colors disabled:opacity-50 whitespace-nowrap";

    return (
        <div className="flex justify-center mb-2" data-testid="hazard-banner">
            <div className="w-11/12">
                <div
                    className="flex items-center gap-3 p-4 bg-red-100 border border-red-400 text-red-700 rounded"
                    role="alert"
                >
                    <ExclamationTriangleIcon className="size-6 shrink-0" />
                    <div className="flex-grow text-left">
                        漏水または電磁弁の故障を検知したため、散水を停止しています
                        {error && <div className="text-sm mt-1">解除に失敗しました: {error}</div>}
                    </div>
                    {confirming ? (
                        <div className="flex items-center gap-2 shrink-0">
                            <span className="text-sm whitespace-nowrap">本当に解除しますか？</span>
                            <button
                                onClick={handleClear}
                                disabled={submitting}
                                className={`${buttonBase} bg-red-500 text-white hover:bg-red-600`}
                            >
                                解除する
                            </button>
                            <button
                                onClick={() => setConfirming(false)}
                                disabled={submitting}
                                className={`${buttonBase} border border-red-500 text-red-500 hover:bg-red-50`}
                            >
                                キャンセル
                            </button>
                        </div>
                    ) : (
                        <button
                            onClick={() => setConfirming(true)}
                            className={`${buttonBase} border border-red-500 text-red-500 hover:bg-red-500 hover:text-white shrink-0`}
                        >
                            解除
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
});

HazardBanner.displayName = "HazardBanner";

export { HazardBanner };
