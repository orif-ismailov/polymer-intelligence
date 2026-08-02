import { LAB_CHAT_POLL_MS, labRequestApi } from "@/entities/lab-request";
import { ThreadChat } from "@/features/thread-chat";

interface LabChatProps {
  companyId: number;
  threadId: number;
}

/** Buyer↔laboratory conversation on one analysis request. */
export function LabChat({ companyId, threadId }: LabChatProps) {
  return (
    <ThreadChat
      companyId={companyId}
      threadId={threadId}
      api={labRequestApi}
      pollMs={LAB_CHAT_POLL_MS}
    />
  );
}
