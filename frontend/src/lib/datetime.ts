import type { Dayjs } from "dayjs";

import dayjs from "./dayjs";

// 表示に使うタイムゾーン（サーバー・設置場所とも JST 運用）
export const DISPLAY_TIMEZONE = "Asia/Tokyo";

// タイムゾーン情報（Z または ±HH:MM / ±HHMM）付きの日時文字列か
const HAS_TZ_OFFSET = /(?:Z|[+-]\d{2}:?\d{2})$/;

// 日時文字列を JST の Dayjs として解釈する。
// naive な文字列（アクチュエータの uptime 等）は JST の時刻とみなして解釈し、
// オフセット付きの文字列は瞬間を保ったまま JST に変換する。
// これによりブラウザのタイムゾーンに依存しない表示になる。
export function parseAsJst(value: string): Dayjs {
    return HAS_TZ_OFFSET.test(value) ? dayjs(value).tz(DISPLAY_TIMEZONE) : dayjs.tz(value, DISPLAY_TIMEZONE);
}

// 現在時刻を JST の Dayjs として返す
export function nowJst(): Dayjs {
    return dayjs().tz(DISPLAY_TIMEZONE);
}

// 標準の日時表示（例: "2026年7月12日 12:34"）
export function formatDateTime(date: Dayjs): string {
    return date.format("LLL");
}

// 現在時刻の標準日時表示（「更新日時」等に使用）
export function formatNowDateTime(): string {
    return formatDateTime(nowJst());
}

// テーブル用の短い日時表示（例: "7月12日 12:34"）。null は "?" を返す。
export function dateText(date: Dayjs | null): string {
    if (date == null) {
        return "?";
    }
    return date.format("M月D日 HH:mm");
}

// 欠落・不正がありうる日時文字列を整形する。空・未取得・"?"（バックエンドの
// センチネル）などの不正値は "?" を返す（dayjs("?") → "Invalid Date" を防ぐ）。
export function formatDateOrFallback(value: string | undefined, method: "format" | "fromNow"): string {
    if (!value) {
        return "?";
    }
    const date = parseAsJst(value);
    if (!date.isValid()) {
        return "?";
    }
    return method === "format" ? formatDateTime(date) : date.fromNow();
}
