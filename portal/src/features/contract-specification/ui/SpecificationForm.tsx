import { useState } from "react";

import { useTranslation } from "react-i18next";

import { contractApi } from "@/entities/contract";
import type {
  Specification,
  SpecificationLineInput,
  SpecificationPayload,
} from "@/entities/contract";
import { detailError } from "@/shared/api";
import {
  Alert,
  Button,
  FormField,
  Input,
  Segmented,
  Textarea,
} from "@/shared/ui";

interface SpecificationFormProps {
  contractId: number;
  onCreated: (spec: Specification) => void;
  onCancel: () => void;
}

const EMPTY_LINE: SpecificationLineInput = {
  product: "",
  qty: "",
  unit: "kg",
  unit_price: "",
};

/**
 * A new «Спецификация № N»: its goods lines and terms.
 *
 * The price is stated with or without VAT — the user's choice: with VAT keeps the
 * agreed total round (as the real specifications do), without VAT makes the ЭСФ
 * match to the tiyin. The server does every sum; nothing is computed here that
 * could disagree with the PDF.
 */
export function SpecificationForm({
  contractId,
  onCreated,
  onCancel,
}: SpecificationFormProps) {
  const { t } = useTranslation();
  const [lines, setLines] = useState<SpecificationLineInput[]>([
    { ...EMPTY_LINE },
  ]);
  const [priceBasis, setPriceBasis] =
    useState<SpecificationPayload["price_basis"]>("with_vat");
  const [vatRate, setVatRate] = useState("12");
  const [paymentMode, setPaymentMode] =
    useState<SpecificationPayload["payment_mode"]>("prepay");
  const [schedule, setSchedule] = useState("");
  const [deliveryDays, setDeliveryDays] = useState("5");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const units = [
    { value: "kg", label: t("specification.units.kg") },
    { value: "t", label: t("specification.units.t") },
    { value: "pcs", label: t("specification.units.pcs") },
  ];
  const complete = lines.every(
    (l) => l.product.trim() && l.qty.trim() && l.unit_price.trim(),
  );

  function setLine(
    index: number,
    patch: Partial<SpecificationLineInput>,
  ): void {
    setLines((current) =>
      current.map((l, i) => (i === index ? { ...l, ...patch } : l)),
    );
  }

  async function submit(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const created = await contractApi.createSpecification(contractId, {
        lines: lines.map((l) => ({
          ...l,
          qty: l.qty.replace(",", "."),
          unit_price: l.unit_price.replace(",", "."),
        })),
        price_basis: priceBasis,
        vat_rate: vatRate,
        payment_mode: paymentMode,
        payment_schedule: paymentMode === "schedule" ? schedule : undefined,
        delivery_days: deliveryDays,
      });
      onCreated(created);
    } catch (err) {
      setError(
        detailError(err) === "invalid_specification"
          ? t("specification.errors.invalid")
          : t("specification.errors.createFailed"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="space-y-4 rounded-md border border-border p-4"
      data-testid="specification-form"
    >
      {lines.map((line, index) => (
        <div
          key={index}
          className="space-y-3 border-b border-border pb-3 last:border-b-0"
          data-testid="specification-line"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-text">
              {t("specification.line", { n: index + 1 })}
            </p>
            {lines.length > 1 ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setLines((current) => current.filter((_, i) => i !== index))
                }
              >
                {t("common.remove")}
              </Button>
            ) : null}
          </div>
          <FormField label={t("specification.product")} required>
            {({ id }) => (
              <Input
                id={id}
                value={line.product}
                onChange={(e) => setLine(index, { product: e.target.value })}
                data-testid="specification-product"
              />
            )}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label={t("specification.qty")} required>
              {({ id }) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  value={line.qty}
                  onChange={(e) => setLine(index, { qty: e.target.value })}
                  data-testid="specification-qty"
                />
              )}
            </FormField>
            <FormField label={t("specification.unit")}>
              {() => (
                <Segmented
                  options={units}
                  value={line.unit}
                  onChange={(unit) => setLine(index, { unit })}
                  ariaLabel={t("specification.unit")}
                />
              )}
            </FormField>
            <FormField label={t("specification.unitPrice")} required>
              {({ id }) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  value={line.unit_price}
                  onChange={(e) =>
                    setLine(index, { unit_price: e.target.value })
                  }
                  data-testid="specification-price"
                />
              )}
            </FormField>
          </div>
        </div>
      ))}
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setLines((c) => [...c, { ...EMPTY_LINE }])}
      >
        {t("specification.addLine")}
      </Button>

      <FormField
        label={t("specification.priceBasis")}
        hint={t(`specification.priceBasisHint.${priceBasis}`)}
      >
        {() => (
          <Segmented
            options={[
              { value: "with_vat", label: t("specification.withVat") },
              { value: "without_vat", label: t("specification.withoutVat") },
            ]}
            value={priceBasis}
            onChange={(v) =>
              setPriceBasis(v as SpecificationPayload["price_basis"])
            }
            ariaLabel={t("specification.priceBasis")}
            data-testid="specification-price-basis"
          />
        )}
      </FormField>
      <FormField label={t("facture.vat")}>
        {() => (
          <Segmented
            options={[
              { value: "12", label: "12%" },
              { value: "0", label: "0%" },
              { value: "none", label: t("facture.noVat") },
            ]}
            value={vatRate}
            onChange={setVatRate}
            ariaLabel={t("facture.vat")}
          />
        )}
      </FormField>
      <FormField label={t("specification.payment")}>
        {() => (
          <Segmented
            options={[
              { value: "prepay", label: t("specification.prepay") },
              { value: "schedule", label: t("specification.schedule") },
            ]}
            value={paymentMode}
            onChange={(v) =>
              setPaymentMode(v as SpecificationPayload["payment_mode"])
            }
            ariaLabel={t("specification.payment")}
          />
        )}
      </FormField>
      {paymentMode === "schedule" ? (
        <FormField label={t("specification.scheduleText")}>
          {({ id }) => (
            <Textarea
              id={id}
              rows={3}
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
            />
          )}
        </FormField>
      ) : null}
      <FormField label={t("specification.deliveryDays")}>
        {({ id }) => (
          <Input
            id={id}
            inputMode="numeric"
            value={deliveryDays}
            onChange={(e) => setDeliveryDays(e.target.value)}
          />
        )}
      </FormField>

      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy || !complete}
          onClick={() => void submit()}
          data-testid="specification-create"
        >
          {busy ? t("common.loading") : t("specification.create")}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onCancel}>
          {t("common.cancel")}
        </Button>
      </div>
    </div>
  );
}
