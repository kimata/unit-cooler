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

    const connect = () => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
        }

        try {
            const eventSource = new EventSource(url);
            eventSourceRef.current = eventSource;

            if (onMessage) {
                eventSource.addEventListener("message", onMessage);
            }

            eventSource.onerror = (event) => {
                if (eventSource.readyState === EventSource.CLOSED) {
                    console.warn("EventSource が閉じられました．再接続します．");
                    reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
                }

                if (onError) {
                    onError(event);
                }
            };
        } catch (error) {
            console.error("EventSource connection failed:", error);
            if (onError) {
                onError(error as Event);
            }
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
