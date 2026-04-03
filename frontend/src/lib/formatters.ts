import { format, formatDistanceToNow } from "date-fns";
import { es } from "date-fns/locale";

export function formatDate(date: string | Date): string {
  return format(new Date(date), "dd MMM yyyy", { locale: es });
}

export function formatDateTime(date: string | Date): string {
  return format(new Date(date), "dd MMM yyyy HH:mm", { locale: es });
}

export function formatRelative(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true, locale: es });
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("es").format(n);
}

export function formatPercent(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount);
}
