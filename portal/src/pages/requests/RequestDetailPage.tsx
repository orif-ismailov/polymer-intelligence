import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import {
  CLIENT_STATUS_KEY,
  useCancelRequest,
  useRequest,
  type StatusHistoryEntry,
} from "@/entities/request";
import { RfqResponseList } from "@/features/rfq-response";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  LinkButton,
  LoadingView,
} from "@/shared/ui";
import { formatDateTime } from "@/shared/lib";

const CANCELLABLE = new Set(["new", "viewed", "in_progress", "offer_sent"]);

/** Collapse the internal history into the client-facing timeline (dedup runs). */
function clientTimeline(history: StatusHistoryEntry[]): { key: string; at: string }[] {
  const out: { key: string; at: string }[] = [];
  for (const h of history) {
    const key = CLIENT_STATUS_KEY[h.to_status] ?? h.to_status;
    const last = out[out.length - 1];
    if (last && last.key === key) continue;
    out.push({ key, at: h.created_at });
  }
  return out;
}

export function RequestDetailPage() {
  const { t } = useTranslation();
  const { requestId: idParam } = useParams<{ requestId: string }>();
  const requestId = idParam ? Number(idParam) : null;
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const requestQuery = useRequest(requestId, companyId);
  const cancel = useCancelRequest(companyId);

  if (requestQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (requestQuery.isError || !requestQuery.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("requests.notFound")}</Alert>
        <LinkButton to="/requests" variant="secondary">
          {t("requests.back")}
        </LinkButton>
      </div>
    );
  }

  const r = requestQuery.data;
  const key = CLIENT_STATUS_KEY[r.status] ?? r.status;
  const timeline = clientTimeline(r.history);
  const canCancel = CANCELLABLE.has(r.status);

  return (
    <div className="space-y-6">
      <LinkButton to="/requests" variant="ghost" className="text-sm">
        ← {t("requests.back")}
      </LinkButton>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex items-start justify-between gap-3">
              <CardTitle>{r.number}</CardTitle>
              <Badge tone="info">{t(`requestStatus.${key}`)}</Badge>
            </CardHeader>
            <CardBody className="grid grid-cols-2 gap-3 text-sm">
              <Spec label={t("requestWizard.product")} value={r.grade_text ?? r.product_text ?? "—"} />
              <Spec label={t("requestWizard.polymer")} value={r.polymer_type ?? "—"} />
              <Spec label={t("requestWizard.volume")} value={`${r.volume} ${r.volume_unit}`} />
              <Spec
                label={t("requestWizard.targetPrice")}
                value={r.target_price != null ? `${r.target_price} ${r.currency}` : "—"}
              />
              <Spec label={t("requestWizard.incoterms")} value={r.incoterms} />
              <Spec label={t("requestWizard.country")} value={r.destination_country} />
              <Spec label={t("requestWizard.city")} value={r.port_or_city ?? "—"} />
              <Spec label={t("requestWizard.urgency")} value={t(`requestWizard.urgencyOpt.${r.urgency}`)} />
              {r.comment ? (
                <div className="col-span-2">
                  <Spec label={t("requestWizard.comment")} value={r.comment} />
                </div>
              ) : null}
            </CardBody>
          </Card>

          {/* Supplier quotes on this RFQ (P2). The buyer accepts one, which
              opens the deal and declines the rest. */}
          {companyId != null && requestId != null ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("rfq.responses")}</CardTitle>
              </CardHeader>
              <CardBody>
                <RfqResponseList companyId={companyId} requestId={requestId} canAccept />
              </CardBody>
            </Card>
          ) : null}

          {canCancel ? (
            <Button
              variant="danger"
              disabled={cancel.isPending}
              onClick={() => requestId != null && cancel.mutate(requestId)}
            >
              {cancel.isPending ? t("common.saving") : t("requests.cancel")}
            </Button>
          ) : null}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{t("requests.timeline")}</CardTitle>
          </CardHeader>
          <CardBody>
            <ol className="space-y-4">
              {timeline.map((entry, i) => (
                <li key={`${entry.key}-${i}`} className="flex gap-3">
                  <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand" />
                  <div>
                    <div className="text-sm font-medium text-text">
                      {t(`requestStatus.${entry.key}`)}
                    </div>
                    <div className="text-xs text-text-muted">{formatDateTime(entry.at)}</div>
                  </div>
                </li>
              ))}
            </ol>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-medium text-text">{value}</dd>
    </div>
  );
}
