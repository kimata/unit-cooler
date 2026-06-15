import {
    ChartBarIcon,
    XCircleIcon,
    SunIcon,
    AdjustmentsHorizontalIcon,
    AdjustmentsVerticalIcon,
    CalendarDaysIcon,
    BoltIcon,
    ClipboardDocumentListIcon,
    PauseCircleIcon,
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
    CalendarDaysIcon,
    BoltIcon,
    ClipboardDocumentListIcon,
    PauseCircleIcon,
};
