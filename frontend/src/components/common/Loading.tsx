import React from "react";

interface LoadingProps {
    size?: "small" | "medium" | "large";
    text?: string;
    className?: string;
}

const Loading = React.memo(({ size = "medium", text = "Loading...", className = "" }: LoadingProps) => {
    const sizeClasses = {
        small: "text-2xl",
        medium: "text-3xl",
        large: "text-4xl",
    };

    return (
        <div className={`text-center ${className}`}>
            <span className={`inline-flex items-center gap-3 font-light ${sizeClasses[size]}`}>
                <svg
                    className="animate-spin size-[1em] text-gray-400"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                >
                    <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                    />
                    <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                </svg>
                <span>{text}</span>
            </span>
        </div>
    );
});

Loading.displayName = "Loading";

export { Loading };
