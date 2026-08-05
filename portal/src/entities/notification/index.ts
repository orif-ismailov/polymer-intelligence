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
    // The BUYER's own request page. Carriers are notified about a broadcast
    // instead, which deep-links into their pool card — a different address for
    // a different reader, so the two cases are separate.
    case "logistics_request":
      return `/cabinet/requests?request=${entityId}`;
    // Its own page: a chat notification has one address and two possible
    // readers, and neither the pool nor the buyer's request page serves both.
    case "logistics_thread":
      return `/cabinet/logistics/threads/${entityId}`;
    // Analysis requests: the pool card for a lab, its own page for a thread.
    case "lab_request":
      return `/cabinet/requests?request=${entityId}`;
    case "lab_thread":
      return `/cabinet/lab/threads/${entityId}`;
    default:
      return null;
  }
}
