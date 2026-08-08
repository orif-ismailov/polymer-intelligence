import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useLabRequests } from "@/entities/lab-request";
import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import { Card, CardBody, EmptyState, FlaskIcon, LoadingView } from "@/shared/ui";

/**
 * The BUYER's own analysis requests to marketplace laboratories — the
 * «Заявки лабораториям» tab of the lab hub.
 *
 * Buyer-only since the broadcast change. A laboratory does not read its
 * incoming work here: it reads the whole pool at `/cabinet/requests`, which is
 * the page that is otherwise permanently empty for a company that files no
 * purchase requests of its own.
 */
export function LabRequestsList({ companyId }: { companyId: number }) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const query = useLabRequests(companyId);

  const rows = query.data ?? [];

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<FlaskIcon size={24} />}
        title={t("labRequest.emptyTitle")}
        description={t("labRequest.emptySentBody")}
      />
    );
  }

  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <Link key={r.id} to={`/cabinet/lab/requests/${r.id}`} className="block">
          <Card>
            <CardBody className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-text">{r.product_text}</p>
                <p className="mt-0.5 text-xs text-text-muted">
                  {r.methods
                    .map((m) => t(`labRequest.methodOptions.${m}`, { defaultValue: m }))
                    .join(", ") || "—"}
                  {" · "}
                  {t("labRequest.responseCount", { count: r.thread_count })}
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
  );
}
