import { useEffect, useRef, useState } from "react";

interface UseEventSourceOptions {
    onMessage?: (event: MessageEvent) => void;
    onError?: (event: Event) => void;
    reconnectInterval?: number;
}

interface UseEventSourceState {
    // SSE の接続状態。null = 接続確立前（初回接続中）、true = 接続中、false = 切断
    connected: boolean | null;
}

export function useEventSource(url: string, options: UseEventSourceOptions = {}): UseEventSourceState {
    const [connected, setConnected] = useState<boolean | null>(null);

    const { onMessage, onError, reconnectInterval = 1000 } = options;

    // NOTE: onMessage / onError は呼び出し側で毎レンダー新しい関数として渡されるため、
    // 直接ハンドラに渡すと初回レンダーのクロージャを掴み続けてしまう（stale closure）。
    // ref 経由で最新のコールバックを参照することで、SSE イベントごとに最新の状態を扱える。
    const onMessageRef = useRef(onMessage);
    const onErrorRef = useRef(onError);

    useEffect(() => {
        onMessageRef.current = onMessage;
        onErrorRef.current = onError;
    }, [onMessage, onError]);

    useEffect(() => {
        let disposed = false;
        let eventSource: EventSource | null = null;
        let reconnectTimer: number | null = null;

        const connect = () => {
            if (disposed) {
                return;
            }
            eventSource?.close();

            try {
                eventSource = new EventSource(url);
            } catch (error) {
                console.error("EventSource connection failed:", error);
                setConnected(false);
                return;
            }

            eventSource.onopen = () => {
                setConnected(true);
            };

            eventSource.addEventListener("message", (event) => {
                onMessageRef.current?.(event);
            });

            eventSource.onerror = (event) => {
                setConnected(false);

                // CONNECTING の場合はブラウザが自動再接続するので任せる。
                // CLOSED の場合のみ自前のタイマーで再接続する。
                if (eventSource?.readyState === EventSource.CLOSED) {
                    console.warn("EventSource が閉じられました．再接続します．");
                    if (reconnectTimer != null) {
                        clearTimeout(reconnectTimer);
                    }
                    reconnectTimer = window.setTimeout(connect, reconnectInterval);
                }

                onErrorRef.current?.(event);
            };
        };

        connect();

        return () => {
            disposed = true;
            eventSource?.close();
            if (reconnectTimer != null) {
                clearTimeout(reconnectTimer);
            }
        };
    }, [url, reconnectInterval]);

    return { connected };
}
