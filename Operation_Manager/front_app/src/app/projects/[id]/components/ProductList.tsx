
import { useEffect, useState } from "react";

type ProductItem = {
  p_id: string;
  uuid: string;
  startTime: string;
  finishTime: string;
};

export default function ProductList({ className = "" }) {
  const [products, setProducts] = useState<ProductItem[]>([]);

  // Product 데이터를 가져오는 함수
  const fetchProducts = async () => {
    try {
      const res = await fetch("/api/products");
      const data = await res.json();
      setProducts(data);
    } catch (error) {
      console.error("제품 정보를 가져오는 데 실패했습니다:", error);
    }
  };

  // 마운트 시 1회 + 이후 주기적 polling
  useEffect(() => {
    fetchProducts(); // 최초 1회

    const intervalId = setInterval(() => {
      fetchProducts();
    }, 60000); // 1분마다 polling

    return () => clearInterval(intervalId); // 언마운트 시 polling 제거
  }, []);

  const showScroll = products.length > 4;

  return (
    <div className={className}>
      <div className="font-semibold text-blue-700 mb-1">Product List</div>
      <div
        className={`space-y-1 pr-1 ${
          showScroll ? "max-h-[190px] overflow-y-auto" : "max-h-none overflow-y-hidden"
        }`}
      >
        {products.map((prod) => (
          <div
            key={prod.p_id}
            className="flex items-center bg-white rounded-xl p-2 shadow border border-gray-100"
            style={{ minHeight: "36px" }}
          >
            {/* p_id */}
            <div className="min-w-[48px] max-w-[60px] mr-2 flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">p_id</div>
              <div className="font-bold text-black text-xs truncate leading-tight">{prod.p_id}</div>
            </div>
            {/* UUID */}
            <div className="min-w-[210px] max-w-[320px] flex-1 mr-2">
              <div className="text-[11px] text-gray-400 leading-none">UUID</div>
              <div className="font-mono text-blue-600 text-xs truncate leading-tight">{prod.uuid}</div>
            </div>
            {/* Start Time */}
            <div className="min-w-[140px] max-w-[170px] mr-2 flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">Start</div>
              <div className="text-xs leading-tight">{prod.startTime}</div>
            </div>
            {/* Finish Time */}
            <div className="min-w-[140px] max-w-[170px] flex-shrink-0">
              <div className="text-[11px] text-gray-400 leading-none">Finish</div>
              <div className="text-xs leading-tight">{prod.finishTime}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}