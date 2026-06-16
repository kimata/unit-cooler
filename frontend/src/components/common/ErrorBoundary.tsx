import React from "react";

import { ErrorMessage } from "./ErrorMessage";

type Props = {
    children: React.ReactNode;
    // クラッシュしたカードを識別するためのラベル（エラー表示に利用）
    label?: string;
};

type State = {
    hasError: boolean;
};

// 1 つのカードがレンダリング中に例外を投げても、画面全体が白画面にならないよう
// 各カードを隔離するためのエラーバウンダリ。
class ErrorBoundary extends React.Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(): State {
        return { hasError: true };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error(`ErrorBoundary (${this.props.label ?? "unknown"}) でエラーを捕捉しました:`, error, info);
    }

    render() {
        if (this.state.hasError) {
            const label = this.props.label;
            return (
                <ErrorMessage message={label ? `${label}の表示中にエラーが発生しました` : "表示中にエラーが発生しました"} />
            );
        }

        return this.props.children;
    }
}

export { ErrorBoundary };
