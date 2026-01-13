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
            <span className={`align-middle ml-4 font-light ${sizeClasses[size]}`}>{text}</span>
        </div>
    );
});

Loading.displayName = "Loading";

export { Loading };
