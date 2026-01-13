import React from "react";

interface PaginationProps {
    page: number;
    total: number;
    limit: number;
    between?: number;
    onChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
    page,
    total,
    limit,
    between = 3,
    onChange,
}) => {
    const totalPages = Math.ceil(total / limit);

    if (totalPages <= 1) return null;

    const getPageNumbers = () => {
        const pages: (number | string)[] = [];
        const start = Math.max(1, page - between);
        const end = Math.min(totalPages, page + between);

        if (start > 1) {
            pages.push(1);
            if (start > 2) pages.push("...");
        }

        for (let i = start; i <= end; i++) {
            pages.push(i);
        }

        if (end < totalPages) {
            if (end < totalPages - 1) pages.push("...");
            pages.push(totalPages);
        }

        return pages;
    };

    const baseClass = "px-3 py-1 rounded border border-gray-300 text-gray-500 transition-colors";
    const activeClass = "bg-gray-500 border-gray-500 text-white";
    const hoverClass = "hover:bg-gray-100";

    return (
        <nav className="flex items-center justify-center gap-1">
            <button
                onClick={() => onChange(page - 1)}
                disabled={page === 1}
                className={`${baseClass} ${hoverClass} disabled:opacity-50 disabled:cursor-not-allowed`}
            >
                &laquo;
            </button>

            {getPageNumbers().map((p, idx) =>
                typeof p === "number" ? (
                    <button
                        key={idx}
                        onClick={() => onChange(p)}
                        className={`${baseClass} ${p === page ? activeClass : hoverClass}`}
                    >
                        {p}
                    </button>
                ) : (
                    <span key={idx} className="px-2">
                        ...
                    </span>
                )
            )}

            <button
                onClick={() => onChange(page + 1)}
                disabled={page === totalPages}
                className={`${baseClass} ${hoverClass} disabled:opacity-50 disabled:cursor-not-allowed`}
            >
                &raquo;
            </button>
        </nav>
    );
};
