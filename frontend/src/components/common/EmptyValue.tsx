import React from "react";

/** データ欠落時の表示 (em-dash) */
export const EmptyValue: React.FC = React.memo(() => (
    <span className="text-gray-400">—</span>
));

EmptyValue.displayName = "EmptyValue";
