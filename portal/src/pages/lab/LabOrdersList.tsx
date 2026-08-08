import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { LabOrderStatusBadge, useLabOrders, type LabOrder } from "@/entities/lab";
import { formatDateTime } from "@/shared/lib";
import {
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  FlaskIcon,
  LinkButton,
  Skeleton,
  SpecItem,
  SpecList,
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

        <SpecList variant="inline">
          {order.sample_volume ? (
            <SpecItem label={t("lab.volume")} value={order.sample_volume} numeric />
          ) : null}
          <SpecItem label={t("lab.created")} value={formatDateTime(order.created_at)} numeric />
          {order.comment ? (
            <SpecItem label={t("lab.comment")} value={order.comment} span={2} />
          ) : null}
          {/* The two things a customer will ask about, so they are on the card
              rather than one click away. */}
          {order.rejected_reason ? (
            <SpecItem label={t("lab.rejectedReason")} value={order.rejected_reason} span={2} />
          ) : null}
          {order.operator_note ? (
            <SpecItem label={t("lab.operatorNote")} value={order.operator_note} span={2} />
          ) : null}
        </SpecList>

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
 * The company's partner-lab orders — the «Анализы через IMEX» tab of the hub.
 *
 * Read-only by design: statuses are moved by an operator after talking to a
 * partner laboratory, and nothing a customer could press here would make one
 * work faster. What they need is the number to quote and where it has got to.
 */
export function LabOrdersList({ companyId }: { companyId: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const orders = useLabOrders(companyId);

  if (orders.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }

  if (orders.isError) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void orders.refetch()}
      />
    );
  }

  if (!orders.data || orders.data.length === 0) {
    return (
      <EmptyState
        icon={<FlaskIcon size={28} />}
        title={t("lab.ordersEmpty")}
        description={t("lab.ordersEmptyBody")}
        action={<LinkButton to="/cabinet/offers">{t("nav.offers")}</LinkButton>}
      />
    );
  }

  return (
    <div className="space-y-3">
      {orders.data.map((order) => (
        <LabOrderCard
          key={order.id}
          order={order}
          onOpen={() => navigate(`/cabinet/offers/${order.offer_id}`)}
        />
      ))}
    </div>
  );
}
