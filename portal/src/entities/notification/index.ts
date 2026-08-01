export type {
  MarkReadBody,
  NotificationPage,
  PortalNotification,
} from "./model/types";
export { notificationApi, notificationKeys } from "./model/api";
export { useMarkRead, useNotifications, useUnreadCount } from "./model/hooks";

/**
 * Deep-link target for a notification's entity/entity_id (or null).
 *
 * The backend stores an opaque `(entity, entity_id)` pair and never a URL, so
 * this function is the ONLY place that maps a notification to a page — which is
 * also why it is the easiest thing to miss when routes move. Everything here is
 * under `/cabinet`: a notification is addressed to a signed-in account, so even
 * the two targets that have public twins (`offer`, `news`) belong on the cabinet
 * side, where the reader has their actions and their chrome.
 */
export function notificationLink(
  entity: string | null,
  entityId: string | null,
): string | null {
  if (!entityId) return entity === "news" ? "/cabinet/news" : null;
  switch (entity) {
    case "request":
      return `/cabinet/requests/${entityId}`;
    // A supplier's view of someone else's RFQ. Deliberately NOT the buyer's
    // `/cabinet/requests/{id}`: that page is company-scoped and a supplier cannot open it.
    case "rfq":
      return `/cabinet/market/requests?rfq=${entityId}`;
    case "inquiry":
      return `/cabinet/inquiries/${entityId}`;
    case "offer":
      return `/market/${entityId}`;
    case "company":
      return `/cabinet/companies/${entityId}`;
    case "news":
      return `/cabinet/news/${entityId}`;
    default:
      return null;
  }
}
