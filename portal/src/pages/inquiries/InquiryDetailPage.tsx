import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useInquiry, useUpdateInquiry } from "@/entities/inquiry";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  LinkButton,
  LoadingView,
  SpecItem,
  SpecList,
  Textarea,
} from "@/shared/ui";

const STATUS_TONE = { pending: "warning", approved: "success", rejected: "danger" } as const;

export function InquiryDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { inquiryId: idParam } = useParams<{ inquiryId: string }>();
  const inquiryId = idParam ? Number(idParam) : null;
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const inquiryQuery = useInquiry(inquiryId);
  const update = useUpdateInquiry(companyId);

  const [editing, setEditing] = useState(false);
  const [quantity, setQuantity] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [message, setMessage] = useState("");

  const inquiry = inquiryQuery.data;
  useEffect(() => {
    if (inquiry) {
      setQuantity(inquiry.quantity != null ? String(inquiry.quantity) : "");
      setTargetPrice(inquiry.target_price != null ? String(inquiry.target_price) : "");
      setMessage(inquiry.message ?? "");
    }
  }, [inquiry]);

  if (inquiryQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (inquiryQuery.isError || !inquiry) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("inquiries.notFound")}</Alert>
        <LinkButton to="/cabinet/inquiries" variant="secondary">
          {t("inquiries.back")}
        </LinkButton>
      </div>
    );
  }

  const product = inquiry.offer.grade_text ?? inquiry.offer.product_text ?? `#${inquiry.offer_id}`;
  const canEdit = companyId != null && inquiry.status !== "rejected";

  function save() {
    if (companyId == null || inquiryId == null) return;
    update.mutate(
      {
        inquiryId,
        payload: {
          company_id: companyId,
          quantity: quantity.trim() || null,
          target_price: targetPrice.trim() || null,
          message: message.trim() || null,
        },
      },
      { onSuccess: () => setEditing(false) },
    );
  }

  return (
    <div className="space-y-6">
      <LinkButton to="/cabinet/inquiries" variant="ghost" className="text-sm">
        ← {t("inquiries.back")}
      </LinkButton>

      <Card>
        <CardHeader className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{product}</CardTitle>
            <button
              type="button"
              onClick={() => navigate(`/cabinet/market/${inquiry.offer_id}`)}
              className="text-sm text-brand hover:underline"
            >
              {t("inquiries.viewOffer")}
            </button>
          </div>
          <Badge tone={STATUS_TONE[inquiry.status]}>{t(`inquiryStatus.${inquiry.status}`)}</Badge>
        </CardHeader>
        <CardBody className="space-y-3">
          {inquiry.edited_at ? (
            <Alert tone="info">{t("inquiries.editedNotice")}</Alert>
          ) : null}

          {!editing ? (
            <SpecList>
              <SpecItem
                label={t("market.quantity")}
                value={
                  inquiry.quantity != null ? `${inquiry.quantity} ${inquiry.qty_unit}` : "—"
                }
                numeric
              />
              <SpecItem
                label={t("market.targetPrice")}
                value={
                  inquiry.target_price != null
                    ? `${inquiry.target_price} ${inquiry.currency ?? ""}`.trim()
                    : "—"
                }
                numeric
              />
              <SpecItem
                label={t("market.message")}
                value={<span className="whitespace-pre-line">{inquiry.message ?? "—"}</span>}
                span={2}
              />
            </SpecList>
          ) : (
            <div className="space-y-3">
              {update.isError ? <Alert tone="danger">{t("inquiries.editFailed")}</Alert> : null}
              <FormField label={t("market.quantity")}>
                {({ id }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                  />
                )}
              </FormField>
              <FormField label={t("market.targetPrice")}>
                {({ id }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={targetPrice}
                    onChange={(e) => setTargetPrice(e.target.value)}
                  />
                )}
              </FormField>
              <FormField label={t("market.message")}>
                {({ id }) => (
                  <Textarea
                    id={id}
                    rows={3}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                  />
                )}
              </FormField>
            </div>
          )}

          {canEdit ? (
            <div className="flex gap-2 pt-1">
              {!editing ? (
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  {t("inquiries.edit")}
                </Button>
              ) : (
                <>
                  <Button disabled={update.isPending} onClick={save}>
                    {update.isPending ? t("common.saving") : t("inquiries.resubmit")}
                  </Button>
                  <Button variant="ghost" onClick={() => setEditing(false)}>
                    {t("common.cancel")}
                  </Button>
                </>
              )}
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
