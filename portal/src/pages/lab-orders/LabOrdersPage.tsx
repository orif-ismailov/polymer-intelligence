import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { LabOrderStatusBadge, useLabOrders, type LabOrder } from "@/entities/lab";
import { formatDateTime } from "@/shared/lib";
import {
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
} from "@/shared/ui";

function LabOrderCard({ order, onOpen }: { order: LabOrder; onOpen: () => void }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="num font-medium text-text">{order.number}</p>
            <p className="truncate text-sm text-text-muted">
              {order.lab_partner_name ?? t("lab.partnerPending")}
            </p>
          </div>
          <LabOrderStatusBadge status={order.status} />
        </div>

        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          {order.sample_volume ? (
            <div className="flex gap-2">
              <dt className="text-text-muted">{t("lab.volume")}:</dt>
              <dd className="text-text">{order.sample_volume}</dd>
            </div>
          ) : null}
          <div className="flex gap-2">
            <dt className="text-text-muted">{t("lab.created")}:</dt>
            <dd className="text-text">{formatDateTime(order.created_at)}</dd>
          </div>
          {order.comment ? (
            <div className="flex min-w-0 gap-2 sm:col-span-2">
              <dt className="shrink-0 text-text-muted">{t("lab.comment")}:</dt>
              <dd className="truncate text-text">{order.comment}</dd>
            </div>
          ) : null}
          {/* The two things a customer will ask about, so they are on the card
              rather than one click away. */}
          {order.rejected_reason ? (
            <div className="flex min-w-0 gap-2 sm:col-span-2">
              <dt className="shrink-0 text-text-muted">{t("lab.rejectedReason")}:</dt>
              <dd className="truncate text-text">{order.rejected_reason}</dd>
            </div>
          ) : null}
          {order.operator_note ? (
            <div className="flex min-w-0 gap-2 sm:col-span-2">
              <dt className="shrink-0 text-text-muted">{t("lab.operatorNote")}:</dt>
              <dd className="truncate text-text">{order.operator_note}</dd>
            </div>
          ) : null}
        </dl>

        {order.offer_id != null ? (
          <button
            type="button"
            onClick={onOpen}
            className="text-sm text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("lab.openOffer")}
          </button>
        ) : null}
      </CardBody>
    </Card>
  );
}

/**
 * The customer's own laboratory orders.
 *
 * Read-only by design: statuses are moved by an operator after talking to a
 * partner laboratory, and nothing a customer could press here would make one
 * work faster. What they need is the number to quote and where it has got to.
 */
export function LabOrdersPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();
  const orders = useLabOrders(activeCompany?.id ?? null);

  if (!activeCompany) {
    return (
      <EmptyState
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
      />
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader title={t("lab.ordersTitle")} subtitle={t("lab.ordersSubtitle")} />

      {orders.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : orders.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void orders.refetch()}
        />
      ) : orders.data && orders.data.length > 0 ? (
        <div className="space-y-3">
          {orders.data.map((order) => (
            <LabOrderCard
              key={order.id}
              order={order}
              onOpen={() => navigate(`/offers/${order.offer_id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t("lab.ordersEmpty")}
          description={t("lab.ordersEmptyBody")}
          action={<LinkButton to="/offers">{t("nav.offers")}</LinkButton>}
        />
      )}
    </div>
  );
}
