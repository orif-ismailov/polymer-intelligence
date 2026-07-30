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
  PageHeader,
  SpecItem,
  SpecList,
  StatusStepper,
  StickyActionBar,
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
    <div className="space-y-5 pb-36 md:pb-0">
      {/* Sheet …47 heads a request with its number and status, not a card. */}
      <PageHeader
        backTo="/requests"
        backLabel={t("requests.back")}
        title={<span className="num">{r.number}</span>}
        badge={<Badge tone="info">{t(`requestStatus.${key}`)}</Badge>}
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="min-w-0 space-y-5 lg:col-span-2">
          <Card>
            <CardBody>
              <SpecList>
                <SpecItem
                  label={t("requestWizard.preview.product")}
                  value={r.grade_text ?? r.product_text ?? "—"}
                />
                <SpecItem
                  label={t("requestWizard.preview.volume")}
                  value={`${r.volume} ${r.volume_unit}`}
                  numeric
                />
                <SpecItem
                  label={t("requestWizard.preview.price")}
                  value={r.target_price != null ? `${r.target_price} ${r.currency}` : "—"}
                  numeric
                />
                <SpecItem label={t("requestWizard.preview.terms")} value={r.incoterms} />
                <SpecItem
                  label={t("requestWizard.params.country")}
                  value={r.destination_country}
                />
                <SpecItem
                  label={t("requestWizard.params.city")}
                  value={r.port_or_city ?? "—"}
                />
                <SpecItem
                  label={t("requestWizard.preview.delivery")}
                  value={t(`requestWizard.urgencyOpt.${r.urgency}`, {
                    defaultValue: r.urgency,
                  })}
                />
                {r.comment ? (
                  <SpecItem label={t("requestWizard.preview.comment")} value={r.comment} span={2} />
                ) : null}
              </SpecList>
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

        </div>

        <Card>
          <CardHeader>
            <CardTitle>{t("requests.timeline")}</CardTitle>
          </CardHeader>
          <CardBody>
            {/* The same vertical timeline the contract and deal rooms use — a
                request's history is the same kind of thing, so it looks it. */}
            <StatusStepper
              steps={timeline.map((entry, i) => ({
                id: `${entry.key}-${i}`,
                label: t(`requestStatus.${entry.key}`),
                hint: formatDateTime(entry.at),
                state: "done" as const,
              }))}
            />
          </CardBody>
        </Card>
      </div>

      {canCancel ? (
        <StickyActionBar>
          <Button
            variant="danger"
            fullWidth
            disabled={cancel.isPending}
            onClick={() => requestId != null && cancel.mutate(requestId)}
          >
            {cancel.isPending ? t("common.saving") : t("requests.cancel")}
          </Button>
        </StickyActionBar>
      ) : null}
    </div>
  );
}
