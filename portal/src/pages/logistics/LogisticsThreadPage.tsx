import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useLogisticsThreads } from "@/entities/logistics-request";
import { LogisticsChat } from "@/features/logistics-chat";
import { ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/cabinet/logistics/threads/:threadId` — one conversation, from either side.
 *
 * Exists because a chat notification has one address and two possible readers.
 * The carrier reads its threads from the pool card and the buyer from their
 * request page, but `notificationLink` cannot know which of them is clicking —
 * so the deep link points here, and the side is derived from the thread's
 * `my_role`, which the API already resolves per reader.
 */
export function LogisticsThreadPage() {
  const { t } = useTranslation();
  const params = useParams<{ threadId: string }>();
  const threadId = params.threadId ? Number(params.threadId) : NaN;

  const { activeCompany, isLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const threads = useLogisticsThreads(companyId);

  if (!Number.isFinite(threadId)) return null;
  if (isLoading || threads.isLoading) return <LoadingView label={t("common.loading")} />;

  const thread = (threads.data ?? []).find((item) => item.id === threadId);
  if (!thread || companyId == null) {
    return (
      <ErrorView title={t("errors.notFound")} message={t("errors.notFoundBody")}>
        <LinkButton to="/cabinet/requests">{t("nav.requests")}</LinkButton>
      </ErrorView>
    );
  }

  // The buyer came from their own request; the carrier came from the pool.
  const backTo =
    thread.my_role === "buyer"
      ? `/cabinet/logistics/requests/${thread.logistics_request_id}`
      : "/cabinet/requests";

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        backTo={backTo}
        backLabel={
          thread.my_role === "buyer"
            ? t("logisticsRequest.myRequests")
            : t("logisticsRequest.poolTitle")
        }
        title={thread.counterparty_name ?? t("logisticsRequest.chat.title")}
        subtitle={`${thread.request_number} · ${thread.cargo_name}`}
      />
      <LogisticsChat companyId={companyId} threadId={thread.id} />
    </div>
  );
}
