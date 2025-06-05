import React, { useState } from "react";

type SearchBarProps = {
  onSearch: (type: string, value: string) => void;
};

export default function SearchBar({ onSearch }: SearchBarProps) {
  const [type, setType] = useState("project_id");
  const [value, setValue] = useState("");

  return (
    <div className="flex gap-2 items-center">
      <div className="relative flex items-center">
        {/* ▼ 화살표 아이콘을 select 왼쪽에 */}
        <span className="absolute left-2 pointer-events-none text-gray-400">
          <svg width="16" height="16" fill="none" viewBox="0 0 20 20">
            <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="2" fill="none" />
          </svg>
        </span>
        <select
          className="border h-10 pl-7 pr-3 bg-gray-50 shadow rounded-none text-sm appearance-none"
          value={type}
          onChange={e => setType(e.target.value)}
          style={{ minWidth: 120 }}
        >
          <option value="project_id">project_id</option>
          <option value="project_name">project_name</option>
        </select>
      </div>
      <input
        className="border px-3 h-10 shadow bg-white rounded-none text-sm"
        type="text"
        value={value}
        placeholder="검색어 입력"
        onChange={e => setValue(e.target.value)}
        style={{ width: 200 }}
      />
      <button
        className="bg-blue-500 hover:bg-blue-700 text-white px-6 h-10 shadow font-semibold rounded-none text-sm"
        onClick={() => onSearch(type, value)}
        style={{ minWidth: 80 }}
      >
        검색
      </button>
    </div>
  );
}