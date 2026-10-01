import type * as ApiResponse from "./ApiResponse";

// 各月の最大日数（年を持たないため、2 月は閏年の 29 日まで許容する）
export const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31] as const;

// 月日の表示（例: "5月1日"）
export function formatMonthDay({ month, day }: ApiResponse.MonthDay): string {
    return `${month}月${day}日`;
}

// 稼働期間の表示（例: "5月1日〜10月31日"）
export function formatSeasonRange({ start, end }: ApiResponse.SeasonSetting): string {
    return `${formatMonthDay(start)}〜${formatMonthDay(end)}`;
}

// 開始 > 終了（年をまたぐ期間）かどうか
export function isAcrossYearEnd({ start, end }: ApiResponse.SeasonSetting): boolean {
    return start.month > end.month || (start.month === end.month && start.day > end.day);
}
