import { useState, useEffect, useCallback } from "react";

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
    // 一度でもデータ取得に成功したか。loading はこれの否定（導出値）にする。
    // 初回フェッチの失敗が続いている間も loading=true のまま安定し（呼び出し側は
    // プレースホルダ表示を維持できる）、一度成功したら以降は loading=false で安定する。
    const [hasLoaded, setHasLoaded] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // 連続失敗回数。同一メッセージの失敗が続いても値が変わるため、
    // リトライ用 effect の再実行トリガーとして機能する。
    const [failureCount, setFailureCount] = useState(0);

    const fetchData = useCallback(async (): Promise<void> => {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            setData(result);
            setHasLoaded(true);
            setError(null);
            setFailureCount(0);
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : "通信に失敗しました";
            // NOTE: 成功するまで error を保持する（フェッチ開始時にはクリアしない）。
            // リトライのたびに error が null ↔ メッセージで振動するのを防ぐ。
            setError(errorMessage);
            setFailureCount((prev) => prev + 1);
            console.error("API fetch error:", err);
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

    // エラー時のリトライ（失敗するたびに failureCount が増えて再スケジュールされる）
    useEffect(() => {
        if (failureCount > 0 && options.retryInterval) {
            const retryId = setTimeout(fetchData, options.retryInterval);
            return () => clearTimeout(retryId);
        }
    }, [failureCount, options.retryInterval, fetchData]);

    return {
        data,
        loading: !hasLoaded,
        error,
        refetch: fetchData,
    };
}
