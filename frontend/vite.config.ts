import process from "node:process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tailwindcss from "@tailwindcss/vite";

// https://vitejs.dev/config/
export default defineConfig({
    base: "/unit-cooler/",
    plugins: [react(), tailwindcss()],
    define: {
        "import.meta.env.VITE_BUILD_DATE": JSON.stringify(new Date().toISOString()),
    },
    build: {
        // バンドルサイズの最適化
        rollupOptions: {
            output: {
                // ベンダーチャンクを分離して効率的なキャッシュを実現
                manualChunks: {
                    vendor: ["react", "react-dom"],
                    charts: ["chart.js", "react-chartjs-2"],
                    utils: ["dayjs", "framer-motion"],
                },
            },
        },
        // 大きなチャンクの警告レベルを調整
        chunkSizeWarningLimit: 1000,
        // ソースマップを無効化してファイルサイズを削減
        sourcemap: false,
        // minifyの最適化（esbuildで高速ビルド）
        minify: "esbuild",
    },
    // 依存関係の事前バンドル最適化
    optimizeDeps: {
        include: ["react", "react-dom", "chart.js", "dayjs", "framer-motion"],
    },
    // 開発サーバー最適化
    server: {
        // npm start 時に API リクエスト（/unit-cooler/api/...）を webui バックエンドへ転送する。
        // 転送先は VITE_API_TARGET で上書き可能（既定は webui の Flask: localhost:5000）。
        proxy: {
            "/unit-cooler/api": {
                target: process.env.VITE_API_TARGET || "http://localhost:5000",
                changeOrigin: true,
            },
        },
        warmup: {
            // よく使われるファイルを事前にウォームアップ
            clientFiles: ["./src/components/**/*.tsx", "./src/lib/**/*.ts"],
        },
    },
});
