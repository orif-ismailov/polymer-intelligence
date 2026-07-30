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
  SpecItem,
  SpecList,
  FlaskIcon,
  RegistryIcon,
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
          icon={<RegistryIcon size={28} />}
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
          icon={<FlaskIcon size={28} />}
          title={t("lab.ordersEmpty")}
          description={t("lab.ordersEmptyBody")}
          action={<LinkButton to="/offers">{t("nav.offers")}</LinkButton>}
        />
      )}
    </div>
  );
}
