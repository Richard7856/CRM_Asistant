/**
 * NotificationPanel — dropdown from bell icon showing recent notifications.
 *
 * Shows unread count badge, lists notifications with action buttons,
 * and marks them as read. Fetches data via React Query.
 */

import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Bot, Building2, ListTodo, Sparkles, AlertTriangle } from "lucide-react";
import {
  listNotifications,
  getUnreadCount,
  markRead,
  markAllRead,
  type Notification,
} from "@/api/notifications";
import { formatRelative } from "@/lib/formatters";

const TYPE_CONFIG: Record<string, { icon: typeof Bell; color: string }> = {
  agent_idle: { icon: AlertTriangle, color: "text-amber-500" },
  agent_created: { icon: Bot, color: "text-indigo-500" },
  department_created: { icon: Building2, color: "text-blue-500" },
  task_assigned: { icon: ListTodo, color: "text-emerald-500" },
  prompt_generated: { icon: Sparkles, color: "text-violet-500" },
  system: { icon: Bell, color: "text-[var(--text-muted)]" },
};

export default function NotificationPanel() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close panel on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const { data: unreadData } = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: getUnreadCount,
    refetchInterval: 30000, // poll every 30s
  });

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => listNotifications(30),
    enabled: open,
  });

  const markReadMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const unreadCount = unreadData?.unread_count ?? 0;

  const handleNotificationClick = (notif: Notification) => {
    if (!notif.is_read) {
      markReadMutation.mutate(notif.id);
    }
    if (notif.action_url) {
      navigate(notif.action_url);
      setOpen(false);
    }
  };

  const config = (type: string) => TYPE_CONFIG[type] ?? TYPE_CONFIG["system"]!;

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(!open)}
        className="neu-sm p-2.5 hover:shadow-none transition-shadow duration-200 active:shadow-[inset_3px_3px_6px_0_var(--neu-dark),inset_-3px_-3px_6px_0_var(--neu-light)]"
      >
        <Bell className="w-4 h-4 text-[var(--text-secondary)]" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center shadow-lg">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 z-50 neu-flat rounded-xl w-96 max-h-[480px] overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--neu-dark)]/10">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              Notificaciones
              {unreadCount > 0 && (
                <span className="ml-2 text-xs font-normal text-[var(--text-muted)]">
                  {unreadCount} sin leer
                </span>
              )}
            </h3>
            {unreadCount > 0 && (
              <button
                onClick={() => markAllReadMutation.mutate()}
                className="text-xs text-indigo-500 hover:text-indigo-600 font-medium flex items-center gap-1"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                Leer todo
              </button>
            )}
          </div>

          {/* Notification list */}
          <div className="overflow-y-auto max-h-[400px]">
            {!notifications || notifications.length === 0 ? (
              <div className="p-8 text-center">
                <Bell className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2 opacity-30" />
                <p className="text-sm text-[var(--text-muted)]">Sin notificaciones</p>
              </div>
            ) : (
              notifications.map((notif) => {
                const { icon: Icon, color } = config(notif.notification_type);
                return (
                  <button
                    key={notif.id}
                    onClick={() => handleNotificationClick(notif)}
                    className={`w-full text-left flex items-start gap-3 px-4 py-3 hover:bg-[var(--neu-dark)]/5 transition-colors ${
                      !notif.is_read ? "bg-indigo-500/5" : ""
                    }`}
                  >
                    <div className={`mt-0.5 p-1.5 rounded-lg bg-[var(--neu-dark)]/5 ${color}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <p className={`text-sm leading-tight ${
                          notif.is_read ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)] font-medium"
                        }`}>
                          {notif.title}
                        </p>
                        {!notif.is_read && (
                          <div className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0 mt-1.5" />
                        )}
                      </div>
                      {notif.body && (
                        <p className="text-xs text-[var(--text-muted)] mt-0.5 line-clamp-2">
                          {notif.body}
                        </p>
                      )}
                      <p className="text-[11px] text-[var(--text-muted)] mt-1">
                        {formatRelative(notif.created_at)}
                      </p>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
