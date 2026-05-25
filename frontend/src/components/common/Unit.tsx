import React from "react";

interface UnitProps {
    children: React.ReactNode;
    className?: string;
}

/** 値の後ろに表示する単位 (℃, %, lx, W/m², mm/h, W, L, 円 等) */
export const Unit = React.memo(({ children, className = "" }: UnitProps) => (
    <small className={`ml-1 text-xs whitespace-nowrap ${className}`}>{children}</small>
));

Unit.displayName = "Unit";
