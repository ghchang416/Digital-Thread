export type ProductItem = {
  p_id: string;
  uuid: string;
  startTime: string;
  finishTime: string;
};

const productList: ProductItem[] = [
  {
    p_id: "P-001",
    uuid: "550e8400-e29b-41d4-a716-446655440000",
    startTime: "2024-06-04 오전 13:30",
    finishTime: "2024-06-04 오전 14:05",
  },
  {
    p_id: "P-002",
    uuid: "550e8400-e29b-41d4-a716-446655440001",
    startTime: "2024-06-04 오전 14:10",
    finishTime: "2024-06-04 오전 14:45",
  },
  {
    p_id: "P-003",
    uuid: "550e8400-e29b-41d4-a716-446655440002",
    startTime: "2024-06-04 오전 15:00",
    finishTime: "2024-06-04 오전 15:35",
  },
  {
    p_id: "P-004",
    uuid: "f7f8d990-516c-4800-93d8-68b410e7e345",
    startTime: "2024-06-04 오전 15:10",
    finishTime: "2024-06-04 오전 15:55",
  },
  {
    p_id: "P-005",
    uuid: "f7f8d990-516c-4800-93d8-68b410e7e345",
    startTime: "2024-06-04 오전 15:10",
    finishTime: "2024-06-04 오전 15:55",
  },
];

export function getAllProducts(): ProductItem[] {
  return productList;
}