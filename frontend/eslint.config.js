import eslint from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import reactHooksPlugin from "eslint-plugin-react-hooks";
import reactRefreshPlugin from "eslint-plugin-react-refresh";

export default [
    eslint.configs.recommended,
    {
        files: ["**/*.{ts,tsx}"],
        languageOptions: {
            parser: tsparser,
            parserOptions: {
                ecmaVersion: 2020,
                sourceType: "module",
            },
            globals: {
                // Browser globals
                console: "readonly",
                document: "readonly",
                window: "readonly",
                fetch: "readonly",
                setTimeout: "readonly",
                clearTimeout: "readonly",
                setInterval: "readonly",
                clearInterval: "readonly",
                EventSource: "readonly",
                Event: "readonly",
                MessageEvent: "readonly",
                HTMLElement: "readonly",
            },
        },
        plugins: {
            "@typescript-eslint": tseslint,
            "react-hooks": reactHooksPlugin,
            "react-refresh": reactRefreshPlugin,
        },
        rules: {
            ...tseslint.configs.recommended.rules,
            ...reactHooksPlugin.configs.recommended.rules,
            "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
            // React Compiler rules - disabled (not using React Compiler)
            "react-hooks/preserve-manual-memoization": "off",
            "react-hooks/set-state-in-effect": "off",
            // Allow namespace for type definitions
            "@typescript-eslint/no-namespace": "off",
        },
    },
    {
        ignores: ["dist/**", "eslint.config.js"],
    },
];
