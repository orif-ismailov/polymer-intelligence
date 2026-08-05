import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useManufacturerThread } from "@/entities/manufacturer";
import { ManufacturerChat } from "@/features/manufacturer-chat";
import { ApiError } from "@/shared/api";
import { Card, CardBody, ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/cabinet/manufacturers/:companyId/chat` — opens (or fetches) the 1:1 thread with a
 * manufacturer, then hands off to the chat UI.
 *
 * The thread comes from a query, not from a mutation fired in an effect. The
 * effect version hung on a permanent spinner — see `useManufacturerThread` for
 * why — and it also had no working retry: the «Повторить» button only cleared a
 * ref, so nothing refetched.
 */
export function ManufacturerChatPage() {
  const { t } = useTranslation();
  const params = useParams<{ companyId: string }>();
  const manufacturerId = params.companyId ? Number(params.companyId) : NaN;
  const validId = Number.isFinite(manufacturerId) ? manufacturerId : null;
  const { activeCompany, isLoading: companyLoading } = useActiveCompany();

  const threadQuery = useManufacturerThread(validId, activeCompany?.id ?? null);

  if (validId == null) return null;

  if (companyLoading || threadQuery.isLoading) {
    return <LoadingView label={t("common.loading")} />;
  }

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const thread = threadQuery.data;
  if (threadQuery.isError || !thread) {
    const notFound = threadQuery.error instanceof ApiError && threadQuery.error.status === 404;
    return (
      <ErrorView
        title={notFound ? t("errors.notFound") : t("errors.loadFailed")}
        message={notFound ? t("errors.notFoundBody") : undefined}
        retryLabel={notFound ? undefined : t("common.retry")}
        onRetry={notFound ? undefined : () => void threadQuery.refetch()}
      >
        <LinkButton to={`/manufacturers/${validId}`}>{t("common.back")}</LinkButton>
      </ErrorView>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        backTo={`/manufacturers/${validId}`}
        backLabel={t("common.back")}
        title={thread.counterparty_name ?? t("manufacturerChat.title")}
        subtitle={t("manufacturerChat.subtitle")}
      />
      <Card>
        <CardBody>
          <ManufacturerChat companyId={activeCompany.id} threadId={thread.id} />
        </CardBody>
      </Card>
    </div>
  );
}
