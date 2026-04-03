import { STATUS_COLORS } from "@/lib/constants";

interface StatusBadgeProps {
  status: string;
  colorMap?: Record<string, string>;
}

/**
 * Neumorphic status badge — soft pill with colored dot and glow.
 * Uses dot-glow-* CSS classes for the subtle ambient glow effect.
 */
export default function StatusBadge({ status, colorMap = STATUS_COLORS }: StatusBadgeProps) {
  const config = colorMap[status] ?? "bg-gray-400 dot-glow-gray";
  const [bgClass, glowClass] = config.includes("dot-glow")
    ? config.split(" ")
    : [config, ""];

  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] neu-pressed-sm px-3 py-1.5">
      <span className={`w-2 h-2 rounded-full ${bgClass} ${glowClass}`} />
      <span className="capitalize">{status.replace(/_/g, " ")}</span>
    </span>
  );
}
