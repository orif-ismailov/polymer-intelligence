import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { CLIENT_STATUS_KEY, useRequests, type RequestSummary } from "@/entities/request";
import { Badge, Card, CardBody, EmptyState, ErrorView, LinkButton, Skeleton } from "@/shared/ui";
import { formatDate } from "@/shared/lib";

const STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "danger" | "info"> = {
  new: "info",
  in_review: "warning",
  offer_received: "success",
  matched: "success",
  closed: "neutral",
  cancelled: "danger",
};

function RequestRow({ request, onOpen }: { request: RequestSummary; onOpen: () => void }) {
  const { t } = useTranslation();
  const key = CLIENT_STATUS_KEY[request.status] ?? request.status;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-lg"
    >
      <Card className="transition-colors hover:border-accent">
        <CardBody className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium text-text">{request.number}</div>
            <div className="text-sm text-text-muted">{formatDate(request.created_at)}</div>
          </div>
          <Badge tone={STATUS_TONE[key] ?? "neutral"}>{t(`requestStatus.${key}`)}</Badge>
        </CardBody>
      </Card>
    </button>
  );
}

export function RequestsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const requestsQuery = useRequests(companyId);

  if (!activeCompany) {
    return (
      <EmptyState title={t("home.noActiveCompany")} description={t("home.noActiveCompanyBody")} />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">{t("requests.title")}</h1>
          <p className="mt-1 text-sm text-text-muted">{t("requests.subtitle")}</p>
        </div>
        <LinkButton to="/requests/new">{t("requests.create")}</LinkButton>
      </div>

      {requestsQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : requestsQuery.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void requestsQuery.refetch()}
        />
      ) : requestsQuery.data && requestsQuery.data.length > 0 ? (
        <div className="space-y-3">
          {requestsQuery.data.map((r) => (
            <RequestRow key={r.id} request={r} onOpen={() => navigate(`/requests/${r.id}`)} />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t("requests.empty")}
          description={t("requests.emptyBody")}
          action={<LinkButton to="/requests/new">{t("requests.create")}</LinkButton>}
        />
      )}
    </div>
  );
}
