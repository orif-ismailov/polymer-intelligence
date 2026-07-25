import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { notificationApi, notificationKeys } from "./api";
import type { MarkReadBody, NotificationPage } from "./types";

const POLL_MS = 30_000;

/** Unread count — polled every 30 s + on window focus (the bell badge). */
export function useUnreadCount(enabled = true) {
  return useQuery<{ count: number }>({
    queryKey: notificationKeys.unread,
    queryFn: () => notificationApi.unreadCount(),
    enabled,
    refetchInterval: POLL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useNotifications(unreadOnly = false, cursor: number | null = null) {
  return useQuery<NotificationPage>({
    queryKey: notificationKeys.list(unreadOnly, cursor),
    queryFn: () =>
      notificationApi.list({ unreadOnly, cursor: cursor ?? undefined }),
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation<{ marked: number }, Error, MarkReadBody>({
    mutationFn: (body) => notificationApi.markRead(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notificationKeys.unread });
      void qc.invalidateQueries({ queryKey: ["notifications", "list"] });
    },
  });
}
