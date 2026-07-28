import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { SampleStatusBadge, useSamples, type SampleRequest } from "@/entities/sample";
import { SampleActions } from "@/features/sample-request";
import { cn } from "@/shared/lib";
import { Card, CardBody, EmptyState, ErrorView, LinkButton, Skeleton } from "@/shared/ui";

type Tab = "incoming" | "sent";

function SampleCard({
  sample,
  companyId,
  onOpenOffer,
}: {
  sample: SampleRequest;
  companyId: number;
  onOpenOffer: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <button
              type="button"
              onClick={onOpenOffer}
              className="truncate text-left font-medium text-text hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {sample.offer_title ?? `#${sample.offer_id}`}
            </button>
            <p className="truncate text-sm text-text-muted">
              {sample.counterparty_name ?? "—"}
            </p>
          </div>
          <SampleStatusBadge status={sample.status} />
        </div>

        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          {sample.qty ? (
            <div className="flex gap-2">
              <dt className="text-text-muted">{t("samples.qty")}:</dt>
              <dd className="num text-text">{sample.qty}</dd>
            </div>
          ) : null}
          <div className="flex min-w-0 gap-2">
            <dt className="shrink-0 text-text-muted">{t("samples.address")}:</dt>
            <dd className="truncate text-text">{sample.delivery_address}</dd>
          </div>
          {/* The two fields that make a shipment checkable rather than claimed. */}
          {sample.courier ? (
            <div className="flex gap-2">
              <dt className="text-text-muted">{t("samples.courier")}:</dt>
              <dd className="text-text">{sample.courier}</dd>
            </div>
          ) : null}
          {sample.tracking_ref ? (
            <div className="flex gap-2">
              <dt className="text-text-muted">{t("samples.tracking")}:</dt>
              <dd className="num text-text">{sample.tracking_ref}</dd>
            </div>
          ) : null}
          {sample.decline_reason ? (
            <div className="flex min-w-0 gap-2 sm:col-span-2">
              <dt className="shrink-0 text-text-muted">{t("samples.reason")}:</dt>
              <dd className="truncate text-text">{sample.decline_reason}</dd>
            </div>
          ) : null}
        </dl>

        <SampleActions sample={sample} companyId={companyId} />
      </CardBody>
    </Card>
  );
}

/**
 * Both sides of the sample flow in one screen — incoming requests to answer and
 * the ones we sent — because a company is regularly both.
 *
 * Which buttons appear is the server's answer (`available_transitions`), not a
 * `my_role === "seller"` branch here.
 */
export function SamplesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const [tab, setTab] = useState<Tab>("incoming");

  const incoming = useSamples(companyId, "incoming");
  const sent = useSamples(companyId, "sent");
  const active = tab === "incoming" ? incoming : sent;

  if (!activeCompany) {
    return (
      <EmptyState
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t("samples.title")}</h1>
        <p className="mt-1 text-sm text-text-muted">{t("samples.subtitle")}</p>
      </div>

      <div className="flex gap-2 border-b border-border">
        {(["incoming", "sent"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === key
                ? "border-brand text-text"
                : "border-transparent text-text-muted hover:text-text",
            )}
          >
            {t(`samples.tab.${key}`)}
          </button>
        ))}
      </div>

      {active.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : active.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void active.refetch()}
        />
      ) : active.data && active.data.length > 0 ? (
        <div className="space-y-3">
          {active.data.map((sample) => (
            <SampleCard
              key={sample.id}
              sample={sample}
              companyId={activeCompany.id}
              onOpenOffer={() => navigate(`/market/${sample.offer_id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t(`samples.empty.${tab}`)}
          description={t("samples.emptyBody")}
          action={
            tab === "sent" ? <LinkButton to="/market">{t("nav.market")}</LinkButton> : undefined
          }
        />
      )}
    </div>
  );
}
