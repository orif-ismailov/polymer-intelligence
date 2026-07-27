export type {
  DealStatus,
  DealRole,
  DealParty,
  DealSummary,
  DealDetail,
  DealCounters,
  DealList,
  DealDocument,
  DealDocumentKind,
  DealEscrow,
  EscrowStatus,
  DealMessage,
  DealMessagePage,
  DealTimelineEntry,
  RfqResponse,
  RfqResponsePayload,
  MarketRequest,
} from "./model/types";
export { dealApi, rfqApi, dealKeys } from "./model/api";
export { useDeals, useDeal, useRfqResponses, useOpenRfqs, DEAL_POLL_MS } from "./model/hooks";
export { DealStatusBadge } from "./ui/DealStatusBadge";
