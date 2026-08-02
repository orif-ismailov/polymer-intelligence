import {
  LOGISTICS_CHAT_POLL_MS,
  logisticsRequestApi,
} from "@/entities/logistics-request";
import { ThreadChat } from "@/features/thread-chat";

interface LogisticsChatProps {
  companyId: number;
  threadId: number;
}

/** Buyer↔carrier conversation on one logistics request. */
export function LogisticsChat({ companyId, threadId }: LogisticsChatProps) {
  return (
    <ThreadChat
      companyId={companyId}
      threadId={threadId}
      api={logisticsRequestApi}
      pollMs={LOGISTICS_CHAT_POLL_MS}
    />
  );
}
