import React from "react";

interface ErrorMessageProps {
    message: string;
    onRetry?: () => void;
    className?: string;
}

const ErrorMessage = React.memo(({ message, onRetry, className = "" }: ErrorMessageProps) => {
    return (
        <div className={`flex justify-center ${className}`} data-testid="error">
            <div className="w-11/12 text-right">
                <div
                    className="flex items-center p-4 bg-red-100 border border-red-400 text-red-700 rounded"
                    role="alert"
                >
                    <div className="flex-grow">{message}</div>
                    {onRetry && (
                        <button
                            className="ml-2 px-2 py-1 text-sm border border-red-500 text-red-500 rounded hover:bg-red-500 hover:text-white transition-colors"
                            onClick={onRetry}
                        >
                            再試行
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
});

ErrorMessage.displayName = "ErrorMessage";

export { ErrorMessage };
