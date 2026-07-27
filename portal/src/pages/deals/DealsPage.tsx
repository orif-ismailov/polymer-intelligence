import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { DealStatusBadge, useDeals } from "@/entities/deal";
import type { DealSummary } from "@/entities/deal";
import { cn, formatDateTime } from "@/shared/lib";
import {
  Badge,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  Skeleton,
} from "@/shared/ui";

type Tab = "all" | "action" | "active" | "closed";

const CLOSED = new Set(["completed", "cancelled"]);

function matches(deal: DealSummary, tab: Tab): boolean {
  if (tab === "action") return deal.needs_action;
  if (tab === "active") return !CLOSED.has(deal.status);
  if (tab === "closed") return CLOSED.has(deal.status);
  return true;
}

function DealCard({ deal, onOpen }: { deal: DealSummary; onOpen: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      <Card className="transition-colors hover:border-brand-line">
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="num truncate text-sm font-semibold text-text">{deal.number}</p>
              <p className="truncate text-xs text-text-muted">
                {t(`deals.role.${deal.role}`)} · {deal.counterparty.name ?? "—"}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {deal.needs_action ? (
                <Badge tone="gold">{t("deals.needsAction")}</Badge>
              ) : null}
              <DealStatusBadge status={deal.status} />
            </div>
          </div>

          <div className="flex flex-wrap items-end justify-between gap-2 border-t border-border pt-3">
            <p className="num text-lg font-semibold leading-tight text-brand">
              {deal.amount ? (
                <>
                  {deal.amount}{" "}
                  <span className="text-sm font-medium text-text-muted">{deal.currency}</span>
                </>
              ) : (
                <span className="text-base text-text-muted">{t("deals.noAmount")}</span>
              )}
            </p>
            <p className="num text-xs text-text-subtle">{formatDateTime(deal.updated_at)}</p>
          </div>
        </CardBody>
      </Card>
    </button>
  );
}

export function DealsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany, isLoading: companyLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const [tab, setTab] = useState<Tab>("all");
  const [role, setRole] = useState<"" | "buyer" | "seller">("");

  const query = useDeals(companyId, role ? { role } : {});
  const all = query.data?.items ?? [];
  const counters = query.data?.counters;
  const items = all.filter((d) => matches(d, tab));

  if (companyLoading) return <Skeleton className="h-40 w-full" />;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const tabs: { id: Tab; count?: number }[] = [
    { id: "all", count: counters?.total },
    { id: "action", count: counters?.needs_action },
    { id: "active", count: counters?.active },
    { id: "closed", count: counters?.closed },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t("deals.title")}</h1>
        <p className="mt-1 text-sm text-text-muted">{t("deals.subtitle")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {tabs.map(({ id, count }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-pressed={tab === id}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
              tab === id
                ? "border-brand-line bg-brand-soft text-brand"
                : "border-border text-text-muted hover:bg-surface-2 hover:text-text",
            )}
          >
            {t(`deals.tabs.${id}`)}
            {count != null ? <span className="num ml-1.5 text-xs">{count}</span> : null}
          </button>
        ))}

        <div className="ml-auto flex gap-2">
          {(["", "buyer", "seller"] as const).map((r) => (
            <button
              key={r || "any"}
              type="button"
              onClick={() => setRole(r)}
              aria-pressed={role === r}
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm transition-colors",
                role === r
                  ? "border-brand-line bg-brand-soft text-brand"
                  : "border-border text-text-muted hover:bg-surface-2 hover:text-text",
              )}
            >
              {r ? t(`deals.role.${r}`) : t("deals.roleAny")}
            </button>
          ))}
        </div>
      </div>

      {query.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : query.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void query.refetch()}
        />
      ) : items.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {items.map((deal) => (
            <DealCard key={deal.id} deal={deal} onOpen={() => navigate(`/deals/${deal.id}`)} />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t("deals.empty")}
          description={t("deals.emptyBody")}
          action={
            <LinkButton to="/market/requests" variant="outline">
              {t("deals.browseRfqs")}
            </LinkButton>
          }
        />
      )}
    </div>
  );
}
