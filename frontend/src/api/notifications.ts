import apiClient from "./client";

export interface Notification {
  id: string;
  agent_id: string | null;
  title: string;
  body: string | null;
  notification_type: string;
  is_read: boolean;
  action_url: string | null;
  metadata_: Record<string, unknown>;
  created_at: string;
}

export interface UnreadCount {
  unread_count: number;
}

export async function listNotifications(limit = 50): Promise<Notification[]> {
  const { data } = await apiClient.get("/notifications/", { params: { limit } });
  return data;
}

export async function getUnreadCount(): Promise<UnreadCount> {
  const { data } = await apiClient.get("/notifications/unread-count");
  return data;
}

export async function markRead(id: string): Promise<Notification> {
  const { data } = await apiClient.patch(`/notifications/${id}/read`);
  return data;
}

export async function markAllRead(): Promise<{ marked_read: number }> {
  const { data } = await apiClient.post("/notifications/read-all");
  return data;
}
