import React from "react";

import { Card, CardHeader } from "./Card";
import { ErrorBoundary } from "./ErrorBoundary";

type Props = {
    // カードのタイトル（ヘッダ表示 + ErrorBoundary のラベルに使用）
    title: string;
    // ヘッダ左に表示するアイコン要素
    icon: React.ReactNode;
    // カード本体（各カードが CardBody を含めて描画する）
    children: React.ReactNode;
};

// ダッシュボード各カードの共通ラッパー。
// 外枠 + ヘッダ(アイコン+タイトル) を共通化し、本体を ErrorBoundary で隔離することで
// 1 枚のカードがクラッシュしても画面全体が白画面にならないようにする。
const DashboardCard = React.memo(({ title, icon, children }: Props) => (
    <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col text-center">
            <Card>
                <CardHeader>
                    {icon}
                    {title}
                </CardHeader>
                <ErrorBoundary label={title}>{children}</ErrorBoundary>
            </Card>
        </div>
    </div>
));

DashboardCard.displayName = "DashboardCard";

export { DashboardCard };
