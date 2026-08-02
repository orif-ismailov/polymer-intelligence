import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useLabRequest, useLabThreads } from "@/entities/lab-request";
import { LabChat } from "@/features/lab-chat";
import { LabRequestSummary } from "@/features/lab-request";
import { formatDate } from "@/shared/lib";
import { coerceLang } from "@/shared/i18n";
import {
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  LoadingView,
  MessageIcon,
  PageHeader,
} from "@/shared/ui";

/**
 * `/cabinet/lab/requests/:requestId` — the BUYER's view of one request.
 *
 * The facts, then one conversation per interested laboratory. Threads are listed
 * rather than merged: each lab has its own room, so a merged transcript would be
 * the one thing the per-laboratory model exists to prevent.
 *
 * A laboratory reaches its own thread from the pool at `/cabinet/requests`, not
 * from here — this page's payload is the buyer's, contact block and all.
 */
export function LabRequestDetailPage() {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const params = useParams<{ requestId: string }>();
  const requestId = params.requestId ? Number(params.requestId) : NaN;

  const { activeCompany, isLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const query = useLabRequest(Number.isFinite(requestId) ? requestId : null, companyId);
  const threads = useLabThreads(companyId);
  const [openThreadId, setOpenThreadId] = useState<number | null>(null);

  if (!Number.isFinite(requestId)) return null;
  if (isLoading || query.isLoading) return <LoadingView label={t("common.loading")} />;

  if (query.isError || !query.data) {
    return (
      <ErrorView title={t("errors.notFound")} message={t("errors.notFoundBody")}>
        <LinkButton to="/cabinet/lab/requests">
          {t("labRequest.myRequests")}
        </LinkButton>
      </ErrorView>
    );
  }

  const request = query.data;
  const mine = (threads.data ?? []).filter(
    (thread) => thread.lab_request_id === request.id,
  );

  return (
    <div className="space-y-5">
      <PageHeader
        backTo="/cabinet/lab/requests"
        backLabel={t("labRequest.myRequests")}
        title={request.product_text}
        subtitle={request.number}
      />
      <LabRequestSummary request={request} />

      <Card>
        <CardBody className="space-y-3">
          <h3 className="text-sm font-semibold text-text">
            {t("labRequest.responsesTitle", { count: mine.length })}
          </h3>

          {mine.length === 0 ? (
            <EmptyState
              icon={<MessageIcon size={24} />}
              title={t("labRequest.noResponses")}
              description={t("labRequest.noResponsesBody")}
            />
          ) : (
            <ul className="space-y-2">
              {mine.map((thread) => (
                <li key={thread.id} className="rounded-md border border-border">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
                    onClick={() =>
                      setOpenThreadId((current) => (current === thread.id ? null : thread.id))
                    }
                    data-testid={`lab-thread-${thread.id}`}
                  >
                    <span className="min-w-0 truncate text-sm font-medium text-text">
                      {thread.counterparty_name ?? t("labRequest.laboratory")}
                    </span>
                    <span className="shrink-0 text-xs text-text-subtle">
                      {formatDate(thread.updated_at, lang)}
                    </span>
                  </button>
                  {openThreadId === thread.id && companyId != null ? (
                    <div className="border-t border-border p-3">
                      <LabChat companyId={companyId} threadId={thread.id} />
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
