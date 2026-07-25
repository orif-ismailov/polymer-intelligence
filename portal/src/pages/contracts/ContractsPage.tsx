import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { ContractStatusBadge, useContracts } from "@/entities/contract";
import type { ContractSummary } from "@/entities/contract";
import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import { Button, Card, CardBody, EmptyState, ErrorView, LoadingView } from "@/shared/ui";

type Tab = "all" | "action" | "active";

const EMPTY: ContractSummary[] = [];

function needsAction(c: ContractSummary): boolean {
  return (
    (c.status === "pending_counterparty" && c.role === "counterparty") ||
    c.status === "pending_signatures"
  );
}

export function ContractsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const [tab, setTab] = useState<Tab>("all");
  const query = useContracts();

  const contracts = query.data ?? EMPTY;
  const filtered = useMemo(() => {
    if (tab === "action") return contracts.filter(needsAction);
    if (tab === "active") return contracts.filter((c) => c.status === "active");
    return contracts;
  }, [contracts, tab]);

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "all", label: t("contracts.tabs.all"), count: contracts.length },
    { id: "action", label: t("contracts.tabs.action"), count: contracts.filter(needsAction).length },
    { id: "active", label: t("contracts.tabs.active"), count: contracts.filter((c) => c.status === "active").length },
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">{t("contracts.title")}</h1>
          <p className="mt-1 text-sm text-text-muted">{t("contracts.subtitle")}</p>
        </div>
        <Button onClick={() => navigate("/contracts/new")} data-testid="contracts-new">
          {t("contracts.create")}
        </Button>
      </div>

      <div className="flex gap-2 border-b border-border">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.id}
            type="button"
            onClick={() => setTab(tabItem.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === tabItem.id
                ? "border-brand font-medium text-text"
                : "border-transparent text-text-muted hover:text-text"
            }`}
            data-testid={`contracts-tab-${tabItem.id}`}
          >
            {tabItem.label} ({tabItem.count})
          </button>
        ))}
      </div>

      {query.isLoading ? <LoadingView label={t("common.loading")} /> : null}
      {query.isError ? (
        <ErrorView title={t("errors.loadFailed")} retryLabel={t("common.retry")} onRetry={() => void query.refetch()} />
      ) : null}

      {!query.isLoading && !query.isError && filtered.length === 0 ? (
        <EmptyState title={t("contracts.empty")} description={t("contracts.emptyBody")} />
      ) : null}

      <div className="space-y-3">
        {filtered.map((c) => (
          <Card key={c.id}>
            <CardBody
              className="flex cursor-pointer items-center justify-between gap-4"
              onClick={() => navigate(`/contracts/${c.id}`)}
              data-testid="contract-row"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-text">{c.title}</p>
                <p className="mt-0.5 text-xs text-text-muted">
                  {t(`contracts.role.${c.role}`)} ·{" "}
                  {c.role === "initiator" ? c.counterparty_name : c.initiator_name} ·{" "}
                  {formatDate(c.created_at, lang)}
                </p>
              </div>
              <ContractStatusBadge status={c.status} />
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}
