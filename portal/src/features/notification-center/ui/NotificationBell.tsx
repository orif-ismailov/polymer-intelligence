import { useState } from "react";

import { Bell } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  notificationLink,
  useMarkRead,
  useNotifications,
  useUnreadCount,
  type PortalNotification,
} from "@/entities/notification";
import { cn } from "@/shared/lib";

export function NotificationBell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const unread = useUnreadCount();
  const list = useNotifications(false, null);
  const markRead = useMarkRead();
  const count = unread.data?.count ?? 0;
  const items = (list.data?.items ?? []).slice(0, 10);

  function openItem(n: PortalNotification) {
    if (!n.read_at) markRead.mutate({ ids: [n.id] });
    setOpen(false);
    const to = notificationLink(n.entity, n.entity_id);
    void navigate(to ?? "/notifications");
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={t("nav.notifications")}
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-text-muted hover:bg-surface-2"
      >
        <Bell size={20} strokeWidth={1.75} aria-hidden="true" />
        {count > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-danger-fg">
            {count > 9 ? "9+" : count}
          </span>
        ) : null}
      </button>

      {open ? (
        <>
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            className="fixed inset-0 z-30 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute end-0 z-40 mt-2 w-80 rounded-lg border border-border bg-surface shadow-lg">
            <div className="flex items-center justify-between border-b border-border px-4 py-2">
              <span className="text-sm font-semibold text-text">{t("nav.notifications")}</span>
              {count > 0 ? (
                <button
                  type="button"
                  onClick={() => markRead.mutate({ all: true })}
                  className="text-xs text-brand hover:underline"
                >
                  {t("notifications.markAllRead")}
                </button>
              ) : null}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {items.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-text-muted">
                  {t("notifications.empty")}
                </p>
              ) : (
                items.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => openItem(n)}
                    className={cn(
                      "flex w-full gap-2 border-b border-border px-4 py-3 text-left last:border-0 hover:bg-surface-2",
                      !n.read_at && "bg-brand-soft/40",
                    )}
                  >
                    {!n.read_at ? (
                      <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand" />
                    ) : (
                      <span className="mt-1 h-2 w-2 shrink-0" />
                    )}
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-text">
                        {t(n.title_key, n.params)}
                      </span>
                      <span className="block truncate text-xs text-text-muted">
                        {t(n.body_key, n.params)}
                      </span>
                    </span>
                  </button>
                ))
              )}
            </div>
            <div className="border-t border-border px-4 py-2 text-center">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  void navigate("/notifications");
                }}
                className="text-sm text-brand hover:underline"
              >
                {t("notifications.viewAll")}
              </button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
