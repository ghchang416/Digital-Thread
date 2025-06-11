import { useState } from "react";

const PAGE_SIZE = 10;

type PaginationProps = {
  totalCount: number;
  pageSize?: number;
  currentPage: number;
  onPageChange: (page: number) => void;
};

export default function ProjectNavBar({
  totalCount,
  pageSize = 10,
  currentPage,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.ceil(totalCount / pageSize);
  // if (totalPages <= 1) return null;

  // 페이지 버튼 최대 5개만 중앙에 노출
  const getPageNumbers = () => {
    const arr = [];
    let start = Math.max(1, currentPage - 2);
    let end = Math.min(totalPages, start + 4);
    if (end - start < 4) start = Math.max(1, end - 4);
    for (let i = start; i <= end; i++) arr.push(i);
    return arr;
  };

  return (
    <div className="flex justify-center mt-6">
      <nav className="inline-flex items-center bg-white rounded-xl px-2 py-1 space-x-1">
        <button
          className="px-2 py-1 rounded disabled:opacity-30"
          disabled={currentPage === 1}
          onClick={() => onPageChange(currentPage - 1)}
        >
          &lt;
        </button>
        {getPageNumbers().map((page) => (
          <button
            key={page}
            className={`px-2 py-1 rounded ${
              page === currentPage
                ? "bg-blue-500 text-white font-bold"
                : "hover:bg-blue-50 text-blue-500"
            }`}
            onClick={() => onPageChange(page)}
          >
            {page}
          </button>
        ))}
        <button
          className="px-2 py-1 rounded disabled:opacity-30"
          disabled={currentPage === totalPages}
          onClick={() => onPageChange(currentPage + 1)}
        >
          &gt;
        </button>
      </nav>
    </div>
  );
}