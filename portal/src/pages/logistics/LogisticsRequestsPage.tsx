import { useState } from "react";

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useLogisticsRequests } from "@/entities/logistics-request";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatDate } from "@/shared/lib";
import {
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LoadingView,
  PageHeader,
  Tabs,
  TruckIcon,
} from "@/shared/ui";

/**
 * `/cabinet/logistics/requests` — both sides of the logistics requests.
 *
 * Exists because the carrier had nowhere to read one. The notification the
 * submit now raises deep-links into this page's detail, and without it that
 * bell rang for a row the recipient could not open — which is the same dead end
 * the profile's «Написать» used to be.
 */
export function LogisticsRequestsPage() {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const [side, setSide] = useState<"sent" | "incoming">("sent");
  const { activeCompany, isLoading } = useActiveCompany();
  const query = useLogisticsRequests(activeCompany?.id ?? null, side);

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")} />
    );
  }

  const rows = query.data ?? [];

  return (
    <div className="space-y-5">
      <PageHeader title={t("logisticsRequest.listTitle")} subtitle={activeCompany.legal_name ?? undefined} />

      {/* `min-w-0` is mandatory on a column holding Tabs — see the design-system note. */}
      <div className="min-w-0">
        <Tabs
          items={[
            { id: "sent", label: t("logisticsRequest.tabSent") },
            { id: "incoming", label: t("logisticsRequest.tabIncoming") },
          ]}
          value={side}
          onChange={(id) => setSide(id as "sent" | "incoming")}
          label={t("logisticsRequest.listTitle")}
        />
      </div>

      {query.isLoading ? <LoadingView label={t("common.loading")} /> : null}

      {!query.isLoading && rows.length === 0 ? (
        <EmptyState
          icon={<TruckIcon size={24} />}
          title={t("logisticsRequest.emptyTitle")}
          description={t(
            side === "sent"
              ? "logisticsRequest.emptySentBody"
              : "logisticsRequest.emptyIncomingBody",
          )}
        />
      ) : null}

      <div className="space-y-2">
        {rows.map((r) => (
          <Link key={r.id} to={`/cabinet/logistics/requests/${r.id}`} className="block">
            <Card>
              <CardBody className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">{r.cargo_name}</p>
                  <p className="mt-0.5 text-xs text-text-muted">
                    {[countryName(r.from_country, lang), countryName(r.to_country, lang)].join(
                      " → ",
                    )}
                    {" · "}
                    {side === "sent" ? r.logistics_name : r.buyer_name}
                  </p>
                </div>
                <div className="text-right">
                  <p className="num text-xs text-text-muted">{r.number}</p>
                  <p className="mt-0.5 text-xs text-text-subtle">
                    {formatDate(r.created_at, lang)}
                  </p>
                </div>
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
