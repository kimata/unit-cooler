import { useState, useCallback } from "react";

import { API_ENDPOINT, postJson, toErrorMessage } from "../lib/api";
import type * as ApiResponse from "../lib/ApiResponse";
import { useApi } from "./useApi";

const SEASON_URL = `${API_ENDPOINT}/proxy/json/api/season`;

// 未取得時のプレースホルダ（通年稼働）
const emptySeason: ApiResponse.SeasonStatus = {
    enabled: false,
    start: { month: 1, day: 1 },
    end: { month: 12, day: 31 },
    in_season: true,
};

// 稼働期間（散水を行う季節）の設定と保存操作を提供するフック。
export function useSeason() {
    const {
        data: season,
        loading,
        refetch,
    } = useApi<ApiResponse.SeasonStatus>(SEASON_URL, emptySeason, {
        // 日付が変わって期間に出入りしたことや、他クライアントからの変更を反映する
        interval: 58000,
    });
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);

    // 保存に成功したら true を返す
    const save = useCallback(
        async (setting: ApiResponse.SeasonSetting): Promise<boolean> => {
            setSaving(true);
            setSaveError(null);
            try {
                await postJson(SEASON_URL, setting);
                await refetch();
                return true;
            } catch (err) {
                setSaveError(toErrorMessage(err));
                console.error("Season API error:", err);
                return false;
            } finally {
                setSaving(false);
            }
        },
        [refetch]
    );

    return { season, loading, saving, saveError, save };
}
