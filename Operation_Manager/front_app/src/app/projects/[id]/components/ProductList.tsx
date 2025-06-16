import { useEffect, useState } from "react";
import { formatDateKST } from "@/utils/time";


type OperationLog = {
  uuid: string;
  index: number;
  toolNumber: number;
  start_time: string;   // ISO 8601 string (예: "2025-06-11T04:21:59.553Z")
  end_time: string;     //
};

type ProductItem = {
  project_id: string;
  machine_id: number;
  product_uuid: string;
  finished: boolean;
  start_time: string;
  finish_time: string;
  operations: OperationLog[];
};

export default function ProductList({ projectId }: { projectId: string }) {
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [error, setError] = useState(false);

  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  const fetchProducts = async () => {
    try {
      // 더미 API
      // const res = await fetch("/api/products"); 

      setError(false); // 호출 시도 전 에러 초기화

      const res = await fetch(`${baseUrl}/api/projects/${projectId}/logs`);
      const data = await res.json();
      setProducts(data.logs);
    } catch (error) {
      console.error("제품 정보를 가져오는 데 실패했습니다:", error);
      setError(true); // 실패 표시
      setProducts([]); // 실패 시 비워두기
    }
  };

  useEffect(() => {
    fetchProducts();
    const intervalId = setInterval(() => {
      fetchProducts();
      console.log("프로덕트 갱신")
    }, 60000);
    return () => clearInterval(intervalId);
  }, []);

  const showScroll = products.length > 4;

  return (
    <div>
      <div className="font-semibold text-blue-700 mb-1">Product List</div>
      <div
        className={`space-y-1 pr-1 ${showScroll ? "max-h-[190px] overflow-y-auto" : "overflow-y-hidden"
          }`}
        style={{ minHeight: "152px" }}
      >
        {error ? (<div className="text-red-400 text-sm text-center py-2">프로덕트를 불러오는데 실패했습니다.</div>) :
          products.length === 0 ? (<div className="text-gray-400 text-sm text-center py-2">프로덕트가 없습니다.</div>) : (
            products.map((prod) => (
              <div
                key={prod.product_uuid}
                className="flex items-center bg-white rounded-xl p-2 shadow border border-gray-100 gap-2"
                style={{ minHeight: "36px" }}
              >
                <div className="min-w-[48px] max-w-[60px] flex-shrink-0">
                  <div className="text-[11px] text-gray-400 leading-none">p_id</div>
                  <div className="font-bold text-black text-xs truncate leading-tight">{prod.project_id}</div>
                </div>
                <div className="min-w-[210px] max-w-[320px] flex-1">
                  <div className="text-[11px] text-gray-400 leading-none">UUID</div>
                  <div className="font-mono text-blue-600 text-xs truncate leading-tight">{prod.product_uuid}</div>
                </div>
                <div className="min-w-[140px] max-w-[170px] flex-shrink-0">
                  <div className="text-[11px] text-gray-400 leading-none">Start</div>
                  <div className="text-xs leading-tight">{formatDateKST(prod.start_time)}</div>
                </div>
                <div className="min-w-[140px] max-w-[170px] flex-shrink-0">
                  <div className="text-[11px] text-gray-400 leading-none">Finish</div>
                  <div className="text-xs leading-tight">{formatDateKST(prod.finish_time)}</div>
                </div>
              </div>
            )))}
      </div>
    </div>
  );
}
