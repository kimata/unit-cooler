import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import macrosPlugin from "vite-plugin-babel-macros";

// https://vitejs.dev/config/
export default defineConfig({
    base: "/unit-cooler/",
    plugins: [react(), macrosPlugin()],
    build: {
        // バンドルサイズの最適化
        rollupOptions: {
            output: {
                // ベンダーチャンクを分離して効率的なキャッシュを実現
                manualChunks: {
                    vendor: ["react", "react-dom"],
                    bootstrap: ["bootstrap", "react-bootstrap"],
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
        include: ["react", "react-dom", "bootstrap", "chart.js", "dayjs", "framer-motion"],
    },
    // 開発サーバー最適化
    server: {
        warmup: {
            // よく使われるファイルを事前にウォームアップ
            clientFiles: ["./src/components/**/*.tsx", "./src/lib/**/*.ts"],
        },
    },
});
