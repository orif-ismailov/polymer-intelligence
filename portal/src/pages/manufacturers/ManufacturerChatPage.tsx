import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useOpenManufacturerThread, type ManufacturerThread } from "@/entities/manufacturer";
import { ManufacturerChat } from "@/features/manufacturer-chat";
import { ApiError } from "@/shared/api";
import { Card, CardBody, ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/manufacturers/:companyId/chat` — opens (or fetches) the 1:1 thread with a
 * manufacturer, then hands off to the chat UI.
 */
export function ManufacturerChatPage() {
  const { t } = useTranslation();
  const params = useParams<{ companyId: string }>();
  const manufacturerId = params.companyId ? Number(params.companyId) : NaN;
  const { activeCompany, isLoading: companyLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const openThread = useOpenManufacturerThread();
  const [thread, setThread] = useState<ManufacturerThread | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current || companyId == null || !Number.isFinite(manufacturerId)) return;
    opened.current = true;
    openThread.mutate(
      { manufacturerId, companyId },
      {
        onSuccess: (data) => setThread(data),
        onError: (err) => setError(err instanceof Error ? err : new Error(String(err))),
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- guarded by `opened` ref, runs once.
  }, [companyId, manufacturerId]);

  if (!Number.isFinite(manufacturerId)) return null;

  if (companyLoading || (openThread.isPending && !thread)) {
    return <LoadingView label={t("common.loading")} />;
  }

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  if (error || !thread) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <ErrorView
        title={notFound ? t("errors.notFound") : t("errors.loadFailed")}
        message={notFound ? t("errors.notFoundBody") : undefined}
        retryLabel={notFound ? undefined : t("common.retry")}
        onRetry={
          notFound
            ? undefined
            : () => {
                opened.current = false;
                setError(null);
              }
        }
      >
        <LinkButton to={`/manufacturers/${manufacturerId}`}>{t("common.back")}</LinkButton>
      </ErrorView>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        backTo={`/manufacturers/${manufacturerId}`}
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
