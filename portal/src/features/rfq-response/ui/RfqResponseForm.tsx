import { useState } from "react";

import { useTranslation } from "react-i18next";

import { rfqApi } from "@/entities/deal";
import { CURRENCIES, INCOTERMS } from "@/shared/config";
import { Alert, Button, FormField, Input, Select, Textarea } from "@/shared/ui";

interface RfqResponseFormProps {
  companyId: number;
  requestId: number;
  onSubmitted: () => void;
  onCancel?: () => void;
}

/**
 * A supplier's quote against a buyer's RFQ.
 *
 * Price and quantity stay strings all the way to the API: they are contract
 * terms, and a float round-trip is a wrong price.
 */
export function RfqResponseForm({
  companyId,
  requestId,
  onSubmitted,
  onCancel,
}: RfqResponseFormProps) {
  const { t } = useTranslation();
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [qty, setQty] = useState("");
  const [qtyUnit, setQtyUnit] = useState("MT");
  const [incoterms, setIncoterms] = useState("");
  const [leadTime, setLeadTime] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const valid = Number(price) > 0 && Number(qty) > 0;

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await rfqApi.respond(companyId, requestId, {
        price,
        currency,
        qty,
        qty_unit: qtyUnit,
        incoterms: incoterms || null,
        lead_time_days: leadTime ? Number(leadTime) : null,
        comment: comment.trim() || null,
      });
      onSubmitted();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error ? <Alert tone="danger" title={error} /> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <FormField label={t("rfq.price")}>
          {({ id }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              inputMode="decimal"
              placeholder="1250.00"
              className="num"
            />
            <Select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              aria-label={t("rfq.currency")}
              options={CURRENCIES.map((c) => ({ value: c, label: c }))}
              className="w-28"
            />
          </div>
          )}
        </FormField>

        <FormField label={t("rfq.qty")}>
          {({ id }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              inputMode="decimal"
              placeholder="20"
              className="num"
            />
            <Input
              value={qtyUnit}
              onChange={(e) => setQtyUnit(e.target.value)}
              aria-label={t("rfq.qtyUnit")}
              className="w-28"
              maxLength={16}
            />
          </div>
          )}
        </FormField>

        <FormField label={t("rfq.incoterms")}>
          {({ id }) => (
          <Select
            id={id}
            value={incoterms}
            onChange={(e) => setIncoterms(e.target.value)}
            options={[
              { value: "", label: t("rfq.incotermsAny") },
              ...INCOTERMS.filter((i) => i !== "unknown").map((i) => ({ value: i, label: i })),
            ]}
          />
          )}
        </FormField>

        <FormField label={t("rfq.leadTime")}>
          {({ id }) => (
          <Input
            id={id}
            value={leadTime}
            onChange={(e) => setLeadTime(e.target.value)}
            inputMode="numeric"
            placeholder="14"
            className="num"
          />
          )}
        </FormField>
      </div>

      <FormField label={t("rfq.comment")}>
        {({ id }) => (
        <Textarea
          id={id}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          placeholder={t("rfq.commentPlaceholder")}
        />
        )}
      </FormField>

      <div className="flex gap-2">
        <Button loading={busy} disabled={!valid} onClick={() => void submit()}>
          {t("rfq.submit")}
        </Button>
        {onCancel ? (
          <Button variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
