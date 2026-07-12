import React from "react";
import type { Dayjs } from "dayjs";

import { dateText } from "../../lib/datetime";
import { EmptyValue } from "./EmptyValue";

interface DateDisplayProps {
    date: Dayjs | null;
    /** "relative" は "N分前" 表示、"absolute" はフォーマット済み日時 */
    format: "relative" | "absolute";
}

/** 日時を <small> でラップして表示。null の場合は EmptyValue を表示 */
export const DateDisplay: React.FC<DateDisplayProps> = ({ date, format }) => (
    <small>{date ? (format === "relative" ? date.fromNow() : dateText(date)) : <EmptyValue />}</small>
);
