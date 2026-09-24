import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { TechRequestStatusBadge, useCompanyTechRequests } from "@/entities/tech-request";
import { formatDate } from "@/shared/lib";
import { EmptyState, LinkButton, LoadingView, PageHeader, PlusIcon } from "@/shared/ui";

/** `/cabinet/tech-requests` — the factory's «нужен технолог» requests. */
export function TechRequestsPage() {
  const { t } = useTranslation();
  const { activeCompanyId } = useActiveCompany();
  const list = useCompanyTechRequests(activeCompanyId);

  return (
    <div className="pb-10">
      <PageHeader
        title={t("techRequest.listTitle")}
        subtitle={t("techRequest.listSubtitle")}
        actions={
          <div className="flex gap-2">
            <LinkButton to="/technologists" variant="outline">
              {t("techRequest.browseExperts")}
            </LinkButton>
            <LinkButton to="/cabinet/tech-requests/new">
              <PlusIcon size={16} />
              {t("techRequest.new")}
            </LinkButton>
          </div>
        }
      />
      {list.isLoading ? (
        <LoadingView label={t("common.loading")} />
      ) : list.data && list.data.length > 0 ? (
        <ul className="mt-5 space-y-3">
          {list.data.map((r) => (
            <li key={r.id}>
              <Link
                to={`/cabinet/tech-requests/${r.id}`}
                className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-brand-line sm:flex-row sm:items-center sm:justify-between"
                data-testid="tech-request-row"
              >
                <div className="min-w-0">
                  <p className="num text-xs text-text-subtle">
                    {r.number} · {formatDate(r.created_at)}
                  </p>
                  <p className="mt-0.5 truncate text-sm font-semibold text-text">
                    {t(`technologists.need.${r.need_type}`)} · {t(`technologists.process.${r.process}`)} · {r.product}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="text-xs text-text-muted">
                    {t("techRequest.offerCount", { count: r.offer_count })}
                  </span>
                  <TechRequestStatusBadge status={r.status} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          className="mt-5"
          title={t("techRequest.empty")}
          description={t("techRequest.emptyBody")}
          action={<LinkButton to="/cabinet/tech-requests/new">{t("techRequest.new")}</LinkButton>}
        />
      )}
    </div>
  );
}
