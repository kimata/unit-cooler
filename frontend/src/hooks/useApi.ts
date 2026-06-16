import { useState, useEffect, useCallback, useRef } from "react";

interface UseApiState<T> {
    data: T;
    loading: boolean;
    error: string | null;
}

interface UseApiOptions {
    interval?: number;
    immediate?: boolean;
    retryInterval?: number; // エラー時のリトライ間隔（ミリ秒）
}

export function useApi<T>(
    url: string,
    initialData: T,
    options: UseApiOptions = {}
): UseApiState<T> & { refetch: () => Promise<void> } {
    const [data, setData] = useState<T>(initialData);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    // NOTE: isFirstLoad を state にすると fetchData の identity が初回ロード完了時に変わり、
    // interval の再生成やマウント直後の二重フェッチを招く。ref に逃がして fetchData を
    // url のみに依存させ、identity を安定させる。
    const isFirstLoadRef = useRef(true);

    const fetchData = useCallback(async (): Promise<void> => {
        const firstLoad = isFirstLoadRef.current;
        try {
            // 初回ロード時のみ loading を true にする
            if (firstLoad) {
                setLoading(true);
            }
            setError(null);

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            setData(result);

            if (firstLoad) {
                isFirstLoadRef.current = false;
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : "通信に失敗しました";
            setError(errorMessage);
            console.error("API fetch error:", err);
        } finally {
            if (firstLoad) {
                setLoading(false);
            }
        }
    }, [url]);

    useEffect(() => {
        if (options.immediate !== false) {
            fetchData();
        }

        if (options.interval) {
            const intervalId = setInterval(fetchData, options.interval);
            return () => clearInterval(intervalId);
        }
    }, [fetchData, options.immediate, options.interval]);

    // エラー時のリトライ
    useEffect(() => {
        if (error && options.retryInterval) {
            const retryId = setTimeout(fetchData, options.retryInterval);
            return () => clearTimeout(retryId);
        }
    }, [error, options.retryInterval, fetchData]);

    return {
        data,
        loading,
        error,
        refetch: fetchData,
    };
}
