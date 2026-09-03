import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { SampleStatusBadge, useSamples, type SampleRequest } from "@/entities/sample";
import { SampleLetterCard } from "@/features/sample-letter";
import { SampleActions } from "@/features/sample-request";
import {
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  SpecItem,
  SpecList,
  Tabs,
  type TabItem,
  PackageOpenIcon,
  RegistryIcon,
} from "@/shared/ui";

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

        <SpecList variant="inline">
          {sample.qty ? <SpecItem label={t("samples.qty")} value={sample.qty} numeric /> : null}
          <SpecItem label={t("samples.address")} value={sample.delivery_address} />
          {/* The two fields that make a shipment checkable rather than claimed. */}
          {sample.courier ? (
            <SpecItem label={t("samples.courier")} value={sample.courier} />
          ) : null}
          {sample.tracking_ref ? (
            <SpecItem label={t("samples.tracking")} value={sample.tracking_ref} numeric />
          ) : null}
          {sample.decline_reason ? (
            <SpecItem label={t("samples.reason")} value={sample.decline_reason} span={2} />
          ) : null}
        </SpecList>

        {/* A request that owes a letter is not with the seller yet, so the card
            sits ABOVE the actions: signing is the only move that matters. */}
        {sample.letter_required ? <SampleLetterCard sample={sample} /> : null}
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
          icon={<RegistryIcon size={28} />}
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
      />
    );
  }

  const sampleTabs: TabItem[] = (["incoming", "sent"] as const).map((key) => ({
    id: key,
    label: t(`samples.tab.${key}`),
  }));

  return (
    <div className="space-y-5">
      <PageHeader title={t("samples.title")} subtitle={t("samples.subtitle")} />

      <Tabs items={sampleTabs} value={tab} onChange={(id) => setTab(id as Tab)} label={t("samples.title")} />

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
          icon={<PackageOpenIcon size={28} />}
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
