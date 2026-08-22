import React from "react";

import { parseAsJst, nowJst } from "../lib/datetime";
import type * as ApiResponse from "../lib/ApiResponse";
import type { OverridePending } from "../hooks/useOverride";
import { PauseCircleIcon, PlayCircleIcon } from "./icons";

// 一時停止時間の選択肢
const DURATION_OPTIONS = [
    { label: "30分", minutes: 30 },
    { label: "1時間", minutes: 60 },
    { label: "2時間", minutes: 120 },
    { label: "4時間", minutes: 240 },
] as const;

// オーバーライド終了予定日時の表示（当日中なら "HH:mm"、日をまたぐ場合は日付付き）
function formatUntil(until: string): string {
    const date = parseAsJst(until);
    if (!date.isValid()) {
        return "?";
    }
    return date.isSame(nowJst(), "day") ? date.format("HH:mm") : date.format("M月D日 HH:mm");
}

type Props = {
    override: ApiResponse.OverrideStatus;
    loading: boolean;
    // 遷移中（停止・再開の反映待ち）はボタンを無効化する
    pending: OverridePending;
    postError: string | null;
    onPause: (minutes: number) => void;
    onResume: () => void;
};

// 散水の手動一時停止（オーバーライド）UI。
// 冷却モードカード内に置き、停止時間を選んで POST → 有効中はバッジ + 再開ボタンを表示する。
// 状態管理は useOverride フック（CoolingMode 側）が担う。
const OverrideControl = React.memo(({ override, loading, pending, postError, onPause, onResume }: Props) => {
    // 状態が一度も取得できていない間は何も出さない（誤った操作 UI の表示を避ける）
    if (loading) {
        return null;
    }

    const submitting = pending != null;

    return (
        <div className="mt-4 pt-3 border-t border-gray-100" data-testid="override-control">
            {override.enabled ? (
                <div className="flex items-center justify-center gap-2 flex-wrap">
                    <span className="inline-flex items-center gap-1 px-3 py-1 rounded bg-amber-100 border border-amber-300 text-amber-800 text-sm">
                        <PauseCircleIcon className="size-4" />
                        手動停止中{override.until != null && `（〜${formatUntil(override.until)} まで）`}
                    </span>
                    <button
                        onClick={onResume}
                        disabled={submitting}
                        className="inline-flex items-center gap-1 px-2 py-1 text-sm rounded border border-gray-300 text-gray-500 hover:bg-gray-100 transition-colors disabled:opacity-50"
                    >
                        <PlayCircleIcon className="size-4" />
                        再開
                    </button>
                </div>
            ) : (
                <div className="flex items-center justify-center gap-1 flex-wrap text-sm text-gray-500">
                    <span className="mr-1">散水を一時停止:</span>
                    {DURATION_OPTIONS.map((option) => (
                        <button
                            key={option.minutes}
                            onClick={() => onPause(option.minutes)}
                            disabled={submitting}
                            className="px-2 py-1 rounded border border-gray-300 text-gray-500 hover:bg-gray-100 transition-colors disabled:opacity-50"
                        >
                            {option.label}
                        </button>
                    ))}
                </div>
            )}
            {postError && <div className="mt-1 text-sm text-red-500">操作に失敗しました: {postError}</div>}
        </div>
    );
});

OverrideControl.displayName = "OverrideControl";

export { OverrideControl };
