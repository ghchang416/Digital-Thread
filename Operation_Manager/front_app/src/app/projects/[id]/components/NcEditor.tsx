"use client";

export default function NcEditor({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-1">
        <div className="font-semibold text-blue-700">NC 에디터</div>
        <div />
      </div>
      <div className="bg-gray-50 border rounded-xl p-2 flex-1 flex flex-col min-h-[100px]">
        <label className="sr-only">NC 코드</label>
        <textarea
          className="flex-1 w-full resize-none bg-transparent outline-none font-mono text-xs leading-tight"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}