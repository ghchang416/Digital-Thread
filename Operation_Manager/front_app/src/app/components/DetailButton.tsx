import React from "react";

type DetailButtonProps = {
  onClick?: () => void;
  children?: React.ReactNode;
  small?: boolean;
};

export default function DetailButton({ onClick, children = "상세보기", small = false }: DetailButtonProps) {
  return (
    <button
      className={`
        ${small ? "px-3 py-1 text-xs" : "px-5 py-2 text-sm"}
        bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-xl shadow transition-all duration-150
      `}
      onClick={onClick}
      style={small ? { minWidth: 72 } : {}}
    >
      {children}
    </button>
  );
}