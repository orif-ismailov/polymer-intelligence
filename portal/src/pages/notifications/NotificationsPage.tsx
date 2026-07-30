import { useEffect } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  notificationLink,
  useMarkRead,
  useNotifications,
  useUnreadCount,
  type PortalNotification,
} from "@/entities/notification";
import {
  Button,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  PageHeader,
  Skeleton,
  BellIcon,
} from "@/shared/ui";
import { cn, formatDateTime } from "@/shared/lib";

export function NotificationsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const list = useNotifications(false, null);
  const unread = useUnreadCount();
  const markRead = useMarkRead();

  // Mark everything read on view (the demo's "mark-read on view" behaviour).
  const hasUnread = (unread.data?.count ?? 0) > 0;
  useEffect(() => {
    if (hasUnread) markRead.mutate({ all: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasUnread]);

  function openItem(n: PortalNotification) {
    const to = notificationLink(n.entity, n.entity_id);
    if (to) void navigate(to);
  }

  const items = list.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("nav.notifications")}
        subtitle={t("notifications.subtitle")}
        actions={
          hasUnread ? (
            <Button variant="secondary" onClick={() => markRead.mutate({ all: true })}>
              {t("notifications.markAllRead")}
            </Button>
          ) : null
        }
      />

      {list.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : list.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void list.refetch()}
        />
      ) : items.length > 0 ? (
        <div className="space-y-2">
          {items.map((n) => {
            const to = notificationLink(n.entity, n.entity_id);
            return (
              <Card
                key={n.id}
                className={cn("transition-colors", to && "cursor-pointer hover:border-brand")}
                role={to ? "button" : undefined}
                tabIndex={to ? 0 : undefined}
                onClick={() => openItem(n)}
                onKeyDown={(e) => {
                  if (to && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    openItem(n);
                  }
                }}
              >
                <CardBody className="flex items-start gap-3">
                  {!n.read_at ? (
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />
                  ) : (
                    <span className="mt-1.5 h-2 w-2 shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-text">
                      {t(n.title_key, n.params)}
                    </div>
                    <div className="text-sm text-text-muted">
                      {t(n.body_key, n.params)}
                    </div>
                    <div className="mt-1 text-xs text-text-muted">
                      {formatDateTime(n.created_at)}
                    </div>
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState icon={<BellIcon size={28} />} title={t("notifications.empty")} description={t("notifications.emptyBody")} />
      )}
    </div>
  );
}
