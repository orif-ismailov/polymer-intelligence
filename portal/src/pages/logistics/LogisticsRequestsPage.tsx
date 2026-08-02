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
  LinkButton,
  TruckIcon,
} from "@/shared/ui";

/**
 * `/cabinet/logistics/requests` — the BUYER's own logistics requests.
 *
 * Buyer-only since the broadcast change. A carrier does not read its incoming
 * work here: it reads the whole pool at `/cabinet/requests`, which is the page
 * that is otherwise permanently empty for a company that files no purchase
 * requests of its own.
 */
export function LogisticsRequestsPage() {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const { activeCompany, isLoading } = useActiveCompany();
  const query = useLogisticsRequests(activeCompany?.id ?? null);

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")} />
    );
  }

  const rows = query.data ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("logisticsRequest.listTitle")}
        subtitle={activeCompany.legal_name ?? undefined}
        actions={
          <LinkButton to="/cabinet/logistics/requests/new">
            {t("logisticsRequest.newRequest")}
          </LinkButton>
        }
      />

      {query.isLoading ? <LoadingView label={t("common.loading")} /> : null}

      {!query.isLoading && rows.length === 0 ? (
        <EmptyState
          icon={<TruckIcon size={24} />}
          title={t("logisticsRequest.emptyTitle")}
          description={t("logisticsRequest.emptySentBody")}
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
                    {t("logisticsRequest.responseCount", { count: r.thread_count })}
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
