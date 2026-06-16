import React from "react";

// ダッシュボード上部のタイトルヘッダ
const Header = React.memo(() => (
    <div className="py-5 px-4 mb-4 bg-gradient-to-r from-blue-50 via-white to-blue-50 border-b border-blue-100 shadow-md">
        <h1 className="text-2xl md:text-3xl font-bold my-0 text-center tracking-widest text-gray-800">
            室外機自動冷却システム
        </h1>
    </div>
));

Header.displayName = "Header";

export { Header };
