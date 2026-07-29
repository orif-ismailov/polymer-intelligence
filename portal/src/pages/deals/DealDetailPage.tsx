import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { DealStatusBadge, useDeal } from "@/entities/deal";
import type { DealParty, DealStatus } from "@/entities/deal";
import {
  DealActionBar,
  DealChat,
  DealDocuments,
  DealEscrowPanel,
  DealLabPanel,
} from "@/features/deal-room";
import { formatDateTime } from "@/shared/lib";
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorView,
  LinkButton,
  LoadingView,
  PageHeader,
  StatusStepper,
  Tabs,
} from "@/shared/ui";
import type { StatusStep, TabItem } from "@/shared/ui";

type Tab = "chat" | "documents" | "timeline" | "contract" | "escrow" | "lab";

/**
 * Marker the backend writes into `cancelled_reason` when escrow refunded the
 * money (`escrow_service.REFUND_REASON`). It is machine-readable on purpose —
 * strip it here rather than showing a client raw developer-speak.
 */
const REFUND_MARKER = "escrow_refund: ";

/** The happy path, in order. Side exits (cancelled/disputed) are not steps. */
const FLOW: DealStatus[] = [
  "negotiation",
  "contract_pending",
  "contract_signed",
  "payment_pending",
  "paid_escrow",
  "shipped",
  "delivered",
  "completed",
];

function PartyCard({ party, label }: { party: DealParty; label: string }) {
  const { t } = useTranslation();
  const initials = (party.name ?? "?").slice(0, 2).toUpperCase();
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-surface-inset text-xs font-semibold text-text-muted">
        {party.logo_url ? (
          <img src={party.logo_url} alt="" className="h-full w-full object-cover" />
        ) : (
          initials
        )}
      </div>
      {/* The badge sits under the name, not beside it: a legal name is long and
          side-by-side truncates it to 'ООО "ХИМ…' at this column width. */}
      <div className="min-w-0">
        <p className="text-xs text-text-subtle">{label}</p>
        <p className="truncate text-sm font-medium text-text" title={party.name ?? undefined}>
          {party.name ?? "—"}
        </p>
        {party.verified ? (
          <Badge variant="verified" className="mt-1">
            {t("market.verified")}
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

export function DealDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ dealId: string }>();
  const dealId = Number(params.dealId);
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const query = useDeal(companyId, Number.isInteger(dealId) ? dealId : null);
  const [tab, setTab] = useState<Tab>("chat");

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;
  if (query.isError || !query.data) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void query.refetch()}
      >
        <LinkButton to="/deals">{t("deals.title")}</LinkButton>
      </ErrorView>
    );
  }

  const deal = query.data;
  const refresh = () => void query.refetch();

  // The stepper stops at whatever the deal actually reached. A cancelled or
  // disputed deal is not on the happy path at all, but it is not "nowhere"
  // either — a buyer whose money was held and refunded must not be shown an
  // empty track, so fall back to the furthest happy-path status its timeline
  // actually recorded.
  const onPath = FLOW.indexOf(deal.status);
  const reached =
    onPath >= 0
      ? onPath
      : Math.max(
          -1,
          ...deal.timeline.map((entry) => FLOW.indexOf(entry.to_status)),
        );
  const steps: StatusStep[] = FLOW.map((status, index) => ({
    id: status,
    label: t(`deals.status.${status}`),
    state: reached < 0 ? "pending" : index < reached ? "done" : index === reached ? "current" : "pending",
  }));

  const tabs: TabItem[] = (["chat", "documents", "timeline", "contract", "escrow", "lab"] as const).map(
    (id) => ({ id, label: t(`deals.tabs.${id}`) }),
  );

  return (
    <div className="space-y-5">
      <PageHeader
        backTo="/deals"
        backLabel={t("deals.title")}
        title={<span className="num">{deal.number}</span>}
        subtitle={`${t(`deals.role.${deal.role}`)} · ${
          deal.amount ? `${deal.amount} ${deal.currency}` : t("deals.noAmount")
        }`}
        badge={<DealStatusBadge status={deal.status} />}
      />

      {deal.status === "cancelled" && deal.cancelled_reason ? (
        <Alert tone="danger" title={t("deals.cancelledTitle")}>
          {deal.cancelled_reason.startsWith(REFUND_MARKER)
            ? `${t("deals.escrow.refundCause")} ${deal.cancelled_reason.slice(REFUND_MARKER.length)}`
            : deal.cancelled_reason}
        </Alert>
      ) : null}
      {deal.status === "disputed" ? (
        <Alert tone="warning" title={t("deals.disputedTitle")}>
          {t("deals.disputedBody")}
        </Alert>
      ) : null}

      {/* items-start: without it the grid stretches both cards to the taller
          one, leaving a large void under the short action bar. */}
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <PartyCard party={deal.buyer} label={t("deals.role.buyer")} />
              <PartyCard party={deal.seller} label={t("deals.role.seller")} />
            </div>
            <div className="border-t border-border pt-4">
              <DealActionBar companyId={companyId as number} deal={deal} onChanged={refresh} />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("deals.progress")}</CardTitle>
          </CardHeader>
          <CardBody>
            <StatusStepper steps={steps} />
          </CardBody>
        </Card>
      </div>

      <Tabs items={tabs} value={tab} onChange={(id) => setTab(id as Tab)} label={deal.number} />

      {tab === "chat" ? (
        <DealChat companyId={companyId as number} dealId={deal.id} />
      ) : tab === "documents" ? (
        <DealDocuments companyId={companyId as number} deal={deal} onChanged={refresh} />
      ) : tab === "timeline" ? (
        <ul className="space-y-2">
          {deal.timeline.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-wrap items-baseline gap-2 rounded-md border border-border px-3 py-2"
            >
              <span className="text-sm font-medium text-text">
                {t(`deals.status.${entry.to_status}`)}
              </span>
              <span className="text-xs text-text-subtle">
                {t(`deals.actor.${entry.actor_kind}`)}
              </span>
              {entry.reason ? (
                <span className="text-sm text-text-muted">— {entry.reason}</span>
              ) : null}
              <span className="num ml-auto text-xs text-text-subtle">
                {formatDateTime(entry.created_at)}
              </span>
            </li>
          ))}
        </ul>
      ) : tab === "contract" ? (
        <Card>
          <CardBody className="space-y-3">
            {deal.contract_id ? (
              <>
                <p className="text-sm text-text-muted">
                  {t("deals.contract.linked", {
                    status: t(`contracts.status.${deal.contract_status ?? "draft"}`),
                  })}
                </p>
                <LinkButton to={`/contracts/${deal.contract_id}`}>
                  {t("deals.contract.open")}
                </LinkButton>
              </>
            ) : (
              <>
                <p className="text-sm text-text-muted">{t("deals.contract.none")}</p>
                {/* Pre-filled from the deal's own agreed terms by the contracts flow. */}
                <LinkButton to={`/contracts/new?deal_id=${deal.id}`}>
                  {t("deals.contract.create")}
                </LinkButton>
              </>
            )}
          </CardBody>
        </Card>
      ) : tab === "escrow" ? (
        <DealEscrowPanel escrow={deal.escrow} />
      ) : (
        <DealLabPanel companyId={companyId as number} dealId={deal.id} />
      )}

      <div>
        <button
          type="button"
          onClick={() => navigate("/deals")}
          className="text-sm text-text-muted underline-offset-2 hover:text-text hover:underline"
        >
          ← {t("deals.title")}
        </button>
      </div>
    </div>
  );
}
