import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { companyHasFeature, useActiveCompany } from "@/entities/company";
import {
  EmptyState,
  LinkButton,
  LoadingView,
  PageHeader,
  RegistryIcon,
  Tabs,
  type TabItem,
} from "@/shared/ui";

import { LabOrdersList } from "./LabOrdersList";
import { LabRequestsList } from "./LabRequestsList";

/**
 * `/cabinet/lab` — the laboratory hub: one nav entry for the two lab flows.
 *
 * «Заявки лабораториям» is the marketplace side (requests answered by verified
 * laboratory companies, in threads); «Анализы через IMEX» is the staff-run
 * partner-lab pipeline (P6), whose completion is the only writer of the gold
 * `lab_verified` badge. The two used to be separate pages and nav entries, and
 * the difference read as a quiz — a client just thinks "my lab stuff".
 *
 * The backends stay separate on purpose; only the surface merged. The route
 * sits behind the WIDER `labOrdering` gate, and the orders tab shows only for
 * roles that also hold `labOrders` — a logistics provider may order an
 * analysis but has no offers for the partner-lab pipeline to verify.
 */
export function LabHubPage() {
  const { t } = useTranslation();
  const { activeCompany, isLoading } = useActiveCompany();
  const [params, setParams] = useSearchParams();

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) {
    return (
      <EmptyState
        icon={<RegistryIcon size={28} />}
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
      />
    );
  }

  const hasOrders = companyHasFeature(activeCompany, "labOrders");
  const tab = params.get("tab") === "orders" && hasOrders ? "orders" : "requests";

  const items: TabItem[] = [
    { id: "requests", label: t("lab.hub.tabRequests") },
    ...(hasOrders ? [{ id: "orders", label: t("lab.hub.tabOrders") }] : []),
  ];

  function switchTab(id: string): void {
    const next = new URLSearchParams(params);
    if (id === "requests") next.delete("tab");
    else next.set("tab", id);
    setParams(next, { replace: true });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("lab.hub.title")}
        subtitle={t("lab.hub.subtitle")}
        actions={
          tab === "requests" ? (
            <LinkButton to="/cabinet/lab/requests/new">{t("labRequest.newRequest")}</LinkButton>
          ) : undefined
        }
      />

      {/* One visible flow needs no tab strip — a single tab is just a label. */}
      {items.length > 1 ? (
        <Tabs items={items} value={tab} onChange={switchTab} label={t("lab.hub.title")} />
      ) : null}

      {tab === "orders" ? (
        <LabOrdersList companyId={activeCompany.id} />
      ) : (
        <LabRequestsList companyId={activeCompany.id} />
      )}
    </div>
  );
}
