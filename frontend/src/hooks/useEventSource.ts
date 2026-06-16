import { useEffect, useRef } from "react";

interface UseEventSourceOptions {
    onMessage?: (event: MessageEvent) => void;
    onError?: (event: Event) => void;
    reconnectInterval?: number;
}

export function useEventSource(url: string, options: UseEventSourceOptions = {}) {
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimeoutRef = useRef<number | null>(null);

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

    const connect = () => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
        }

        try {
            const eventSource = new EventSource(url);
            eventSourceRef.current = eventSource;

            eventSource.addEventListener("message", (event) => {
                onMessageRef.current?.(event);
            });

            eventSource.onerror = (event) => {
                if (eventSource.readyState === EventSource.CLOSED) {
                    console.warn("EventSource が閉じられました．再接続します．");
                    reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
                }

                onErrorRef.current?.(event);
            };
        } catch (error) {
            console.error("EventSource connection failed:", error);
            onErrorRef.current?.(error as Event);
        }
    };

    useEffect(() => {
        connect();

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        };
        // connect is intentionally excluded to prevent infinite loops
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [url]);

    return {
        reconnect: connect,
        close: () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        },
    };
}
