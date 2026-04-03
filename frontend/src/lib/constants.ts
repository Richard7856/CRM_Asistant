/**
 * Color maps for StatusBadge.
 * Format: "bg-color dot-glow-color" — the badge component splits on space.
 * Neumorphic badges use muted Tailwind colors with CSS glow classes.
 */

export const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-400 dot-glow-green",
  idle: "bg-amber-400 dot-glow-yellow",
  busy: "bg-blue-400 dot-glow-blue",
  error: "bg-red-400 dot-glow-red",
  offline: "bg-gray-400 dot-glow-gray",
  maintenance: "bg-violet-400 dot-glow-purple",
};

export const PRIORITY_COLORS: Record<string, string> = {
  low: "bg-gray-400 dot-glow-gray",
  medium: "bg-blue-400 dot-glow-blue",
  high: "bg-orange-400 dot-glow-yellow",
  critical: "bg-red-500 dot-glow-red",
};

export const LOG_LEVEL_COLORS: Record<string, string> = {
  debug: "text-gray-400",
  info: "text-blue-400",
  warning: "text-amber-400",
  error: "text-red-400",
  critical: "text-red-500",
};

export const TASK_STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-400 dot-glow-gray",
  assigned: "bg-blue-400 dot-glow-blue",
  in_progress: "bg-indigo-500 dot-glow-blue",
  review: "bg-violet-400 dot-glow-purple",
  completed: "bg-emerald-400 dot-glow-green",
  failed: "bg-red-400 dot-glow-red",
  cancelled: "bg-gray-300 dot-glow-gray",
};
