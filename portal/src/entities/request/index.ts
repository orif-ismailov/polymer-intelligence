export type {
  RequestDetail,
  RequestFile,
  RequestPayload,
  RequestStatus,
  RequestSummary,
  StatusHistoryEntry,
} from "./model/types";
export { requestApi, requestKeys } from "./model/api";
export {
  useCancelRequest,
  useCreateRequest,
  useRequest,
  useRequests,
} from "./model/hooks";

/** Internal RequestStatus → client-facing label key (mirror CLIENT_STATUS_MAP). */
export const CLIENT_STATUS_KEY: Record<string, string> = {
  new: "new",
  viewed: "in_review",
  in_progress: "in_review",
  offer_sent: "offer_received",
  matched: "matched",
  closed: "closed",
  cancelled: "cancelled",
};
