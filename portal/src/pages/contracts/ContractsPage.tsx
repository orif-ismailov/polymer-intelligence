import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { ContractStatusBadge, useContracts } from "@/entities/contract";
import type { ContractSummary } from "@/entities/contract";
import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import {
  Button,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LoadingView,
  PageHeader,
  Tabs,
  type TabItem,
  ContractSheetIcon,
} from "@/shared/ui";

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

  const tabItems: TabItem[] = tabs.map((tabItem) => ({
    id: tabItem.id,
    label: tabItem.label,
    count: tabItem.count,
    testId: `contracts-tab-${tabItem.id}`,
  }));

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("contracts.title")}
        subtitle={t("contracts.subtitle")}
        actions={
          <Button onClick={() => navigate("/cabinet/contracts/new")} data-testid="contracts-new">
            {t("contracts.create")}
          </Button>
        }
      />

      <Tabs items={tabItems} value={tab} onChange={(id) => setTab(id as Tab)} label={t("contracts.title")} />

      {query.isLoading ? <LoadingView label={t("common.loading")} /> : null}
      {query.isError ? (
        <ErrorView title={t("errors.loadFailed")} retryLabel={t("common.retry")} onRetry={() => void query.refetch()} />
      ) : null}

      {!query.isLoading && !query.isError && filtered.length === 0 ? (
        <EmptyState icon={<ContractSheetIcon size={28} />} title={t("contracts.empty")} description={t("contracts.emptyBody")} />
      ) : null}

      <div className="space-y-3">
        {filtered.map((c) => (
          <Card key={c.id}>
            <CardBody
              className="flex cursor-pointer items-center justify-between gap-4"
              onClick={() => navigate(`/cabinet/contracts/${c.id}`)}
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
