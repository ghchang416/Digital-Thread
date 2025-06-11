

import { useRouter } from "next/navigation";
import DetailButton from "./DetailButton";

type ProjectListItemProps = {
  id: string;
  name: string;
  onDetail?: () => void;
};

export default function ProjectListItem({ id, name, onDetail }: ProjectListItemProps) {
  const router = useRouter();
  return (
    <div
      className="
        flex items-center justify-between
        bg-white rounded-xl p-3 mb-0.2 shadow
        border border-gray-100
        hover:border-blue-300 hover:shadow-md
        transition-all duration-200
        h-16
      "
      style={{ minHeight: "3.5rem" }}
    >
      <div>
        <div className="text-[11px] text-gray-400">Project ID</div>
        <div className="font-mono text-blue-700 text-sm font-semibold">{id}</div>
      </div>
      <div>
        <div className="text-[11px] text-gray-400">Project Name</div>
        <div className="font-semibold text-gray-800 text-sm">{name}</div>
      </div>
      <DetailButton onClick={() => {router.push(`/projects/${id}?name=${encodeURIComponent(name)}`);}} small />
    </div>
  );
}