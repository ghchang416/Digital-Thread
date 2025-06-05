'use client';

import React, { useState } from "react";

type NcEditorProps = {
  ncCode: string;
};

export default function NcEditor({ ncCode }: NcEditorProps) {
  const [value, setValue] = useState(ncCode);

  // ncCode prop이 바뀌면 textarea도 업데이트 (수정)
  React.useEffect(() => {
    setValue(ncCode);
  }, [ncCode]);

  return (
    <div className="flex flex-col h-full">
      {/* 상단 제목 바 */}
      <div className="flex items-center justify-between mb-1">
        <div className="font-semibold text-blue-700">NC 에디터</div>
        <div />
      </div>
      {/* 에디터 박스: h-full */}
      <div className="bg-gray-50 border rounded-xl p-2 flex-1 flex flex-col min-h-[100px]">
        <label className="sr-only">NC 코드</label>
        <textarea
          className="flex-1 w-full resize-none bg-transparent outline-none font-mono text-xs leading-tight"
          value={value}
          onChange={e => setValue(e.target.value)}
        />
      </div>
    </div>
  );
}