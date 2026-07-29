export type {
  MarkReadBody,
  NotificationPage,
  PortalNotification,
} from "./model/types";
export { notificationApi, notificationKeys } from "./model/api";
export { useMarkRead, useNotifications, useUnreadCount } from "./model/hooks";

/** Deep-link target for a notification's entity/entity_id (or null). */
export function notificationLink(
  entity: string | null,
  entityId: string | null,
): string | null {
  if (!entityId) return entity === "news" ? "/news" : null;
  switch (entity) {
    case "request":
      return `/requests/${entityId}`;
    // A supplier's view of someone else's RFQ. Deliberately NOT `/requests/{id}`:
    // that page is the BUYER's, company-scoped, and a supplier cannot open it.
    case "rfq":
      return `/market/requests?rfq=${entityId}`;
    case "inquiry":
      return `/inquiries/${entityId}`;
    case "offer":
      return `/market/${entityId}`;
    case "company":
      return `/companies/${entityId}`;
    case "news":
      return `/news/${entityId}`;
    default:
      return null;
  }
}
