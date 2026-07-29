import { api } from "@/shared/api";

import type { MarkReadBody, NotificationPage } from "./types";

export const notificationApi = {
  list: (opts: { unreadOnly?: boolean; cursor?: number; limit?: number } = {}): Promise<NotificationPage> =>
    api.get<NotificationPage>("/portal/notifications", {
      query: { unread_only: opts.unreadOnly, cursor: opts.cursor, limit: opts.limit },
    }),

  unreadCount: (): Promise<{ count: number }> =>
    api.get<{ count: number }>("/portal/notifications/unread-count"),

  markRead: (body: MarkReadBody): Promise<{ marked: number }> =>
    api.post<{ marked: number }>("/portal/notifications/read", body),
};

export const notificationKeys = {
  list: (unreadOnly: boolean, cursor: number | null) =>
    ["notifications", "list", unreadOnly, cursor] as const,
  unread: ["notifications", "unread"] as const,
};
