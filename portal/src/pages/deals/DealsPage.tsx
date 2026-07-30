import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { DealStatusBadge, useDeals } from "@/entities/deal";
import type { DealSummary } from "@/entities/deal";
import { formatDateTime } from "@/shared/lib";
import {
  Badge,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  Tabs,
  type TabItem,
  TraderIcon,
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

  const scopeTabs: TabItem[] = (["all", "action", "active", "closed"] as const).map((id) => ({
    id,
    label: t(`deals.tabs.${id}`),
    count: { all: counters?.total, action: counters?.needs_action, active: counters?.active, closed: counters?.closed }[id],
  }));

  const roleTabs: TabItem[] = (["", "buyer", "seller"] as const).map((r) => ({
    id: r,
    label: r ? t(`deals.role.${r}`) : t("deals.roleAny"),
  }));

  return (
    <div className="space-y-5">
      <PageHeader title={t("deals.title")} subtitle={t("deals.subtitle")} />

      {/* Scope on the left, party on the right — one chip row, as in the sheets. */}
      <div className="flex flex-wrap items-center gap-2">
        <Tabs
          variant="pill"
          items={scopeTabs}
          value={tab}
          onChange={(id) => setTab(id as Tab)}
          label={t("deals.title")}
        />
        <Tabs
          className="ms-auto"
          variant="pill"
          items={roleTabs}
          value={role}
          onChange={(id) => setRole(id as "" | "buyer" | "seller")}
          label={t("deals.roleAny")}
        />
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
          icon={<TraderIcon size={28} />}
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
