import { useState } from "react";

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useCreateInquiry } from "@/entities/inquiry";
import type { MarketOfferDetail } from "@/entities/market";
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
  Textarea,
} from "@/shared/ui";

const INQUIRY_STATUS_TONE = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
} as const;

/**
 * True when a filled-in field cannot survive the wire.
 *
 * `quantity`/`target_price` land in `Decimal … gt=0` (`OfferRequestCreate`), so
 * "500 тонн" or "0" comes back a 422 the buyer can only read as a generic
 * failure. Empty is fine — it is sent as null. Same rule as the offer wizard's
 * positive-number check (`features/offer-wizard/model/validation.ts`).
 */
function notPositiveNumber(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed === "") return false;
  const parsed = Number(trimmed);
  return !Number.isFinite(parsed) || parsed <= 0;
}

interface OfferInquiryCardProps {
  /** The AUTHENTICATED offer payload — `is_own`, `accepts_rfq`, `my_inquiries`. */
  offer: MarketOfferDetail;
  companyId: number | null;
}

/**
 * The RFQ form and the buyer's own inquiries on this offer.
 *
 * Mounts only for a signed-in visitor — every branch here reads a field the
 * public payload does not carry, and it posts. On `/market/:id` it therefore
 * appears after hydration, leaving the server-rendered HTML the same for a
 * crawler, an anonymous visitor and a signed-in one.
 */
export function OfferInquiryCard({ offer, companyId }: OfferInquiryCardProps) {
  const { t } = useTranslation();
  const createInquiry = useCreateInquiry(companyId);

  const [quantity, setQuantity] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [message, setMessage] = useState("");

  const canSendRfq = companyId != null && !offer.is_own && offer.accepts_rfq;
  const quantityError = notPositiveNumber(quantity) ? t("market.quantityInvalid") : null;
  const targetPriceError = notPositiveNumber(targetPrice) ? t("market.targetPriceInvalid") : null;
  const inquiryError =
    createInquiry.error?.code === "network" || createInquiry.error?.status === 0
      ? t("common.network")
      : createInquiry.error?.status === 429
        ? t("market.inquiryRateLimited")
        : createInquiry.error?.code === "rfq_not_accepted"
          ? t("market.detail.rfqNotAccepted")
          : createInquiry.error?.status === 400 && createInquiry.error.message
            ? createInquiry.error.message
            : createInquiry.isError
              ? t("market.inquiryFailed")
              : null;

  function submit(): void {
    if (companyId == null) return;
    createInquiry.mutate(
      {
        offerId: offer.id,
        payload: {
          company_id: companyId,
          quantity: quantity.trim() || null,
          // The offer's own unit and currency, or the server records its defaults
          // (MT / none) and staff read "500" against a KG listing as 500 tonnes.
          qty_unit: offer.qty_unit,
          target_price: targetPrice.trim() || null,
          currency: offer.currency,
          message: message.trim() || null,
        },
      },
      {
        onSuccess: () => {
          setQuantity("");
          setTargetPrice("");
          setMessage("");
        },
      },
    );
  }

  /** Clear a stale success/error banner as soon as the buyer starts a new inquiry. */
  function edit(setter: (value: string) => void): (value: string) => void {
    return (value) => {
      if (createInquiry.isSuccess || createInquiry.isError) createInquiry.reset();
      setter(value);
    };
  }

  return (
    <>
      {offer.my_inquiries.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("market.myInquiries")}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {offer.my_inquiries.map((inq) => (
              <Link
                key={inq.id}
                to={`/cabinet/inquiries/${inq.id}`}
                className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm hover:border-brand"
              >
                <span className="text-text-muted">{inq.message ?? `#${inq.id}`}</span>
                <Badge tone={INQUIRY_STATUS_TONE[inq.status]}>
                  {t(`inquiryStatus.${inq.status}`)}
                </Badge>
              </Link>
            ))}
          </CardBody>
        </Card>
      ) : null}

      {/* scroll-mt clears the sticky topbar when «Написать продавцу» jumps here. */}
      <Card id="inquiry" className="scroll-mt-20">
        <CardHeader>
          <CardTitle>{t("market.detail.requestRfq")}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {offer.is_own ? (
            <Alert tone="info">{t("market.ownOffer")}</Alert>
          ) : companyId == null ? (
            <Alert tone="warning">{t("market.selectCompanyHint")}</Alert>
          ) : !offer.accepts_rfq ? (
            // The server refuses this too (422 `rfq_not_accepted`). Greying only the
            // hero button while leaving a working form below it meant a seller's
            // opt-out held in one place on the page and not in the other.
            <Alert tone="info">{t("market.detail.rfqNotAccepted")}</Alert>
          ) : (
            <>
              {createInquiry.isSuccess ? (
                <Alert tone="success">{t("market.inquirySent")}</Alert>
              ) : null}
              {inquiryError ? <Alert tone="danger">{inquiryError}</Alert> : null}
              <FormField label={t("market.quantity")} error={quantityError}>
                {({ id, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={quantity}
                    onChange={(e) => edit(setQuantity)(e.target.value)}
                    placeholder={offer.qty_unit}
                    aria-describedby={describedBy}
                  />
                )}
              </FormField>
              <FormField label={t("market.targetPrice")} error={targetPriceError}>
                {({ id, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={targetPrice}
                    onChange={(e) => edit(setTargetPrice)(e.target.value)}
                    placeholder={offer.currency}
                    aria-describedby={describedBy}
                  />
                )}
              </FormField>
              <FormField label={t("market.message")}>
                {({ id }) => (
                  <Textarea
                    id={id}
                    rows={3}
                    value={message}
                    onChange={(e) => edit(setMessage)(e.target.value)}
                  />
                )}
              </FormField>
              <Button
                fullWidth
                disabled={
                  !canSendRfq ||
                  createInquiry.isPending ||
                  quantityError != null ||
                  targetPriceError != null ||
                  (!quantity.trim() && !message.trim())
                }
                onClick={submit}
                data-testid="inquiry-submit"
              >
                {createInquiry.isPending ? t("common.saving") : t("market.sendInquiry")}
              </Button>
            </>
          )}
        </CardBody>
      </Card>
    </>
  );
}
