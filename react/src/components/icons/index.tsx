import {
    ChartBarIcon,
    XCircleIcon,
    SunIcon,
    AdjustmentsHorizontalIcon,
    AdjustmentsVerticalIcon,
    BeakerIcon,
    CalendarDaysIcon,
    BoltIcon,
    ClipboardDocumentListIcon,
} from "@heroicons/react/24/solid";

// カスタム GitHub アイコン（Heroicons にブランドアイコンなし）
export const GitHubIcon = ({ className = "size-6" }: { className?: string }) => (
    <svg className={className} fill="currentColor" viewBox="0 0 16 16">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
);

// カスタム Toggle On アイコン
export const ToggleOnIcon = ({ className = "size-6" }: { className?: string }) => (
    <svg className={className} fill="currentColor" viewBox="0 0 16 16">
        <path d="M5 3a5 5 0 0 0 0 10h6a5 5 0 0 0 0-10H5zm6 9a4 4 0 1 1 0-8 4 4 0 0 1 0 8z" />
    </svg>
);

// カスタム Toggle Off アイコン
export const ToggleOffIcon = ({ className = "size-6" }: { className?: string }) => (
    <svg className={className} fill="currentColor" viewBox="0 0 16 16">
        <path d="M11 4a4 4 0 0 1 0 8H8a4.992 4.992 0 0 0 2-4 4.992 4.992 0 0 0-2-4h3zm-6 8a4 4 0 1 1 0-8 4 4 0 0 1 0 8zM0 8a5 5 0 0 0 5 5h6a5 5 0 0 0 0-10H5a5 5 0 0 0-5 5z" />
    </svg>
);

// カスタム水滴アイコン（散水量用）
export const DropletIcon = ({ className = "size-6" }: { className?: string }) => (
    <svg className={className} fill="currentColor" viewBox="0 0 16 16">
        <path d="M8 16a6 6 0 0 0 6-6c0-1.655-1.122-2.904-2.432-4.362C10.254 4.176 8.75 2.503 8 0c-.75 2.503-2.254 4.176-3.568 5.638C3.122 7.096 2 8.345 2 10a6 6 0 0 0 6 6z" />
    </svg>
);

// カスタム雪の結晶アイコン（冷却モード用）
export const SnowflakeIcon = ({ className = "size-6" }: { className?: string }) => (
    <svg className={className} fill="currentColor" viewBox="0 0 16 16">
        <path d="M8 0a.5.5 0 0 1 .5.5v1.293l1.146-1.147a.5.5 0 0 1 .708.708L9.207 2.5H10.5a.5.5 0 0 1 0 1H9.207l1.147 1.146a.5.5 0 0 1-.708.708L8.5 4.207V5.5a.5.5 0 0 1-1 0V4.207L6.354 5.354a.5.5 0 1 1-.708-.708L6.793 3.5H5.5a.5.5 0 0 1 0-1h1.293L5.646 1.354a.5.5 0 1 1 .708-.708L7.5 1.793V.5A.5.5 0 0 1 8 0z" />
        <path d="M8 5a.5.5 0 0 1 .5.5v1.293l1.146-1.147a.5.5 0 0 1 .708.708L9.207 7.5H10.5a.5.5 0 0 1 0 1H9.207l1.147 1.146a.5.5 0 0 1-.708.708L8.5 9.207V10.5a.5.5 0 0 1-1 0V9.207l-1.146 1.147a.5.5 0 0 1-.708-.708L6.793 8.5H5.5a.5.5 0 0 1 0-1h1.293L5.646 6.354a.5.5 0 1 1 .708-.708L7.5 6.793V5.5A.5.5 0 0 1 8 5z" />
        <path d="M8 10a.5.5 0 0 1 .5.5v1.293l1.146-1.147a.5.5 0 0 1 .708.708L9.207 12.5H10.5a.5.5 0 0 1 0 1H9.207l1.147 1.146a.5.5 0 0 1-.708.708L8.5 14.207V15.5a.5.5 0 0 1-1 0v-1.293l-1.146 1.147a.5.5 0 0 1-.708-.708L6.793 13.5H5.5a.5.5 0 0 1 0-1h1.293l-1.147-1.146a.5.5 0 0 1 .708-.708L7.5 11.793V10.5A.5.5 0 0 1 8 10z" />
    </svg>
);

// カスタム温度計アイコン（センサー値用）
export const ThermometerIcon = ({ className = "size-6" }: { className?: string }) => (
    <svg className={className} fill="currentColor" viewBox="0 0 16 16">
        <path d="M8 14a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z" />
        <path d="M8 0a2.5 2.5 0 0 0-2.5 2.5v7.55a3.5 3.5 0 1 0 5 0V2.5A2.5 2.5 0 0 0 8 0zM6.5 2.5a1.5 1.5 0 1 1 3 0v7.987l.167.15a2.5 2.5 0 1 1-3.333 0l.166-.15V2.5z" />
    </svg>
);

// Heroicons から再エクスポート
export {
    ChartBarIcon,
    XCircleIcon,
    SunIcon,
    AdjustmentsHorizontalIcon,
    AdjustmentsVerticalIcon,
    BeakerIcon,
    CalendarDaysIcon,
    BoltIcon,
    ClipboardDocumentListIcon,
};
