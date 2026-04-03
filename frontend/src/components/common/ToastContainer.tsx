/**
 * Neumorphic toast notifications — bottom-right.
 * Raised pills with accent color indicator instead of full background tint.
 */

import { useToastStore } from "@/stores/toastStore";
import { X, CheckCircle, AlertCircle, Info } from "lucide-react";

const ICONS = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
};

const ACCENT_COLORS = {
  success: "text-emerald-400",
  error: "text-red-400",
  info: "text-blue-400",
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-3 max-w-sm">
      {toasts.map((toast) => {
        const Icon = ICONS[toast.type];
        return (
          <div
            key={toast.id}
            className="neu-flat flex items-start gap-3 px-4 py-3.5 animate-slide-in"
          >
            <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${ACCENT_COLORS[toast.type]}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)]">{toast.title}</p>
              {toast.message && (
                <p className="text-xs mt-0.5 text-[var(--text-secondary)]">{toast.message}</p>
              )}
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="flex-shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
