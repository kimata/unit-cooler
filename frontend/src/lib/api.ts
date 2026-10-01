// Web UI バックエンド API のベースパス。
// フロントエンド全体でここから import して使う（重複定義を避ける）。
export const API_ENDPOINT = "/unit-cooler/api";

// JSON API へ POST し、レスポンスの JSON を返す。HTTP エラーは例外にする。
export async function postJson<T>(url: string, body?: object): Promise<T> {
    const response = await fetch(url, {
        method: "POST",
        ...(body != null && {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }),
    });
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
}

// 例外を UI 表示用のメッセージに変換する
export function toErrorMessage(err: unknown): string {
    return err instanceof Error ? err.message : "通信に失敗しました";
}
