import React from "react";

interface CardProps {
    children: React.ReactNode;
    className?: string;
}

/** カード全体のラッパー */
export const Card: React.FC<CardProps> = ({ children, className = "" }) => (
    <div className={`bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col h-full ${className}`}>
        {children}
    </div>
);

/** カードのヘッダ (アイコン + タイトル) */
export const CardHeader: React.FC<CardProps> = ({ children, className = "" }) => (
    <div className={`px-4 py-3 border-b border-gray-200 bg-gray-50 rounded-t-lg ${className}`}>
        <h4 className="my-0 font-normal flex items-center justify-center gap-2">{children}</h4>
    </div>
);

/** カードの本体 */
export const CardBody: React.FC<CardProps> = ({ children, className = "" }) => (
    <div className={`p-4 flex-1 ${className}`}>{children}</div>
);
