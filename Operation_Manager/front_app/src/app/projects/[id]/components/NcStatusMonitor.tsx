"use client";

import { useEffect } from "react";

type NcData = {
  id: string;
  workplan: string;
  fileName: string;
  status: string;
  code: string;
};
type Props = {
  ncList: NcData[];
  setNcList: (updater: (prev: NcData[]) => NcData[]) => void;
};

export default function NcStatusMonitor({ ncList, setNcList }: Props) {
  useEffect(() => {
    const intervalId = setInterval(async () => {
      const targets = ncList.filter((nc) => nc.status === "가공대기");

      if (targets.length === 0) return;

      const updatedStatuses = await Promise.all(
        targets.map(async (nc) => {
          const res = await fetch(`/api/nc/${nc.id}`);
          const data = await res.json(); // { id, status }
          return data;
        })
      );

      setNcList((prevList) =>
        prevList.map((nc) => {
          const updated = updatedStatuses.find((u) => u.id === nc.id);
          return updated ? { ...nc, status: updated.status } : nc;
        })
      );
    }, 5000);

    return () => clearInterval(intervalId);
  }, [ncList, setNcList]);

  return null; // 렌더링은 하지 않음
}