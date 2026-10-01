import React, { useState, useCallback } from "react";

import type * as ApiResponse from "../lib/ApiResponse";
import { DAYS_IN_MONTH, formatMonthDay, formatSeasonRange, isAcrossYearEnd } from "../lib/season";
import { CalendarDaysIcon } from "./icons";

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

const selectClass =
    "px-1 py-1 rounded border border-gray-300 bg-white text-gray-700 disabled:opacity-50 disabled:bg-gray-50";
const buttonClass = "px-2 py-1 rounded border transition-colors disabled:opacity-50";

type MonthDaySelectProps = {
    // aria-label に使う名前（"開始" / "終了"）
    label: string;
    value: ApiResponse.MonthDay;
    disabled: boolean;
    onChange: (value: ApiResponse.MonthDay) => void;
};

// 月・日のセレクトボックス（年は扱わない）
const MonthDaySelect = ({ label, value, disabled, onChange }: MonthDaySelectProps) => {
    const maxDay = DAYS_IN_MONTH[value.month - 1];

    return (
        <span className="inline-flex items-center gap-1 whitespace-nowrap">
            <select
                aria-label={`${label}月`}
                className={selectClass}
                value={value.month}
                disabled={disabled}
                onChange={(e) => {
                    const month = Number(e.target.value);
                    // 月を変えたとき、その月に存在しない日は月末に丸める
                    onChange({ month, day: Math.min(value.day, DAYS_IN_MONTH[month - 1]) });
                }}
            >
                {MONTHS.map((month) => (
                    <option key={month} value={month}>
                        {month}
                    </option>
                ))}
            </select>
            月
            <select
                aria-label={`${label}日`}
                className={selectClass}
                value={value.day}
                disabled={disabled}
                onChange={(e) => onChange({ month: value.month, day: Number(e.target.value) })}
            >
                {Array.from({ length: maxDay }, (_, i) => i + 1).map((day) => (
                    <option key={day} value={day}>
                        {day}
                    </option>
                ))}
            </select>
            日
        </span>
    );
};

type Props = {
    season: ApiResponse.SeasonStatus;
    loading: boolean;
    saving: boolean;
    saveError: string | null;
    // 保存に成功したら true を返す
    onSave: (setting: ApiResponse.SeasonSetting) => Promise<boolean>;
};

// 稼働期間（散水を行う季節）の設定 UI。
// 冷却モードカード内に置き、通常は現在の設定を 1 行で表示し、「変更」で編集フォームを開く。
// 状態管理は useSeason フック（CoolingMode 側）が担う。
const SeasonControl = React.memo(({ season, loading, saving, saveError, onSave }: Props) => {
    // 編集中の設定。null は編集していない（表示モード）。
    const [draft, setDraft] = useState<ApiResponse.SeasonSetting | null>(null);

    const handleSave = useCallback(async () => {
        if (draft != null && (await onSave(draft))) {
            setDraft(null);
        }
    }, [draft, onSave]);

    // 設定が一度も取得できていない間は何も出さない（誤った設定の表示・上書きを避ける）
    if (loading) {
        return null;
    }

    return (
        <div
            className="mt-3 pt-3 border-t border-gray-100 text-sm text-gray-500"
            data-testid="season-control"
        >
            {draft == null ? (
                <div className="flex items-center justify-center gap-2 flex-wrap">
                    <span className="inline-flex items-center gap-1">
                        <CalendarDaysIcon className="size-4" />
                        稼働期間:
                    </span>
                    <span data-testid="season-range">
                        {season.enabled ? formatSeasonRange(season) : "通年"}
                    </span>
                    <button
                        onClick={() =>
                            setDraft({ enabled: season.enabled, start: season.start, end: season.end })
                        }
                        className={`${buttonClass} border-gray-300 hover:bg-gray-100`}
                    >
                        変更
                    </button>
                </div>
            ) : (
                <div className="flex flex-col items-center gap-2" data-testid="season-editor">
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={draft.enabled}
                            disabled={saving}
                            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
                        />
                        稼働期間を限定する（期間外は散水しない）
                    </label>
                    <div className="flex items-center justify-center gap-2 flex-wrap">
                        <MonthDaySelect
                            label="開始"
                            value={draft.start}
                            disabled={saving || !draft.enabled}
                            onChange={(start) => setDraft({ ...draft, start })}
                        />
                        <span>〜</span>
                        <MonthDaySelect
                            label="終了"
                            value={draft.end}
                            disabled={saving || !draft.enabled}
                            onChange={(end) => setDraft({ ...draft, end })}
                        />
                    </div>
                    {draft.enabled && isAcrossYearEnd(draft) && (
                        <small className="text-gray-400" data-testid="season-across-year">
                            年をまたぐ期間（{formatMonthDay(draft.start)}〜翌年{formatMonthDay(draft.end)}
                            ）として扱います
                        </small>
                    )}
                    <div className="flex items-center justify-center gap-2">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className={`${buttonClass} border-[#5e7e9b] bg-[#5e7e9b] text-white hover:opacity-90`}
                        >
                            保存
                        </button>
                        <button
                            onClick={() => setDraft(null)}
                            disabled={saving}
                            className={`${buttonClass} border-gray-300 hover:bg-gray-100`}
                        >
                            キャンセル
                        </button>
                    </div>
                    {saveError && <div className="text-red-500">保存に失敗しました: {saveError}</div>}
                </div>
            )}
        </div>
    );
});

SeasonControl.displayName = "SeasonControl";

export { SeasonControl };
