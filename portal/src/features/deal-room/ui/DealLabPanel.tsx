import { useState } from "react";

import { useTranslation } from "react-i18next";

import { LabOrderStatusBadge, useCreateLabOrder, useLabOrders } from "@/entities/lab";
import { formatDateTime } from "@/shared/lib";
import {
  Alert,
  Button,
  Card,
  CardBody,
  EmptyState,
  FormField,
  Input,
  Textarea,
  FlaskIcon,
} from "@/shared/ui";

interface DealLabPanelProps {
  companyId: number;
  dealId: number;
}

/**
 * Order an analysis of the material in flight, from inside the Trade Room
 * (FR-L2).
 *
 * The result does NOT land here — it goes into the deal's Documents tab as a
 * `lab_passport`, through the deals context's own upload path. This panel is
 * the request and its status; the document lives where every other deal
 * document lives, so nobody has to learn a second place to look.
 */
export function DealLabPanel({ companyId, dealId }: DealLabPanelProps) {
  const { t } = useTranslation();
  const [volume, setVolume] = useState("");
  const [comment, setComment] = useState("");
  const orders = useLabOrders(companyId);
  const create = useCreateLabOrder(companyId);

  const mine = (orders.data ?? []).filter((o) => o.deal_id === dealId);
  const live = mine.find((o) => o.status !== "rejected" && o.status !== "done") ?? null;

  return (
    <div className="space-y-4">
      {mine.length === 0 ? (
        <EmptyState icon={<FlaskIcon size={28} />} title={t("lab.dealNoneTitle")} description={t("lab.dealNoneBody")} />
      ) : (
        <div className="space-y-3">
          {mine.map((order) => (
            <Card key={order.id}>
              <CardBody className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="num font-medium text-text">{order.number}</p>
                  <p className="text-sm text-text-muted">
                    {order.lab_partner_name ?? t("lab.partnerPending")}
                  </p>
                  <p className="text-xs text-text-subtle">
                    {formatDateTime(order.created_at)}
                  </p>
                  {order.status === "done" ? (
                    <p className="mt-1 text-sm text-text-muted">{t("lab.dealResultInDocs")}</p>
                  ) : null}
                </div>
                <LabOrderStatusBadge status={order.status} />
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {live ? null : (
        <Card>
          <CardBody className="space-y-3">
            <p className="text-sm text-text-muted">{t("lab.orderCopy")}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label={t("lab.volume")}>
                {({ id }) => (
                  <Input id={id} value={volume} onChange={(e) => setVolume(e.target.value)} />
                )}
              </FormField>
            </div>
            <Textarea
              rows={3}
              value={comment}
              placeholder={t("lab.orderCommentPlaceholder")}
              onChange={(e) => setComment(e.target.value)}
            />
            {create.error ? <Alert tone="danger">{t("errors.generic")}</Alert> : null}
            <Button
              loading={create.isPending}
              onClick={() =>
                create.mutate(
                  {
                    deal_id: dealId,
                    sample_volume: volume.trim() || null,
                    comment: comment.trim() || null,
                  },
                  {
                    onSuccess: () => {
                      setVolume("");
                      setComment("");
                    },
                  },
                )
              }
            >
              {t("lab.orderSubmit")}
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
