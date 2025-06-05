'use client';

import { useRouter } from "next/navigation";

export default function MainButton({ className = "" }) {
  const router = useRouter();
  return (
    <button
      className={`bg-blue-400 hover:bg-blue-600 text-white font-semibold rounded-xl px-5 py-2 shadow ${className}`}
      onClick={() => router.push("/")}
    >
      Main으로 이동
    </button>
  );
}