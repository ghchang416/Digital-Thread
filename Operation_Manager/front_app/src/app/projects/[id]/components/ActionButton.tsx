type ActionButtonProps = {
  onClick?: () => void;
  children: React.ReactNode;
  color?: "blue" | "gray";
  disabled?: boolean;
};

export default function ActionButton({
  onClick,
  children,
  color = "gray",
  disabled = false,
}: ActionButtonProps) {
  const colorClass =
    color === "blue"
      ? "bg-blue-500 hover:bg-blue-600 text-white"
      : "bg-gray-200 hover:bg-gray-300 text-gray-800";

  const disabledClass = disabled ? "opacity-50 cursor-not-allowed" : "";

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`px-5 py-2 rounded-xl font-semibold shadow ${colorClass} ${disabledClass} transition-all duration-150`}
    >
      {children}
    </button>
  );
}