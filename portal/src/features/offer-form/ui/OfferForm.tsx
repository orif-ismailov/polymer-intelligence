import { type FormEvent } from "react";

import { useTranslation } from "react-i18next";

import type { CompanyOffer } from "@/entities/offer";
import { AVAILABILITY, CURRENCIES, INCOTERMS, QTY_UNITS } from "@/shared/config";
import { useEnumLabels } from "@/shared/i18n";
import { Alert, Button, FormField, Input, Select, Textarea } from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";

import {
  EMPTY_OFFER_FORM,
  formToPayload,
  offerToForm,
  useOfferForm,
} from "../model/useOfferForm";
import { isNotVerifiedError, useSaveOffer } from "../model/useSaveOffer";

interface OfferFormProps {
  companyId: number;
  /** Existing offer to edit, or null to create. */
  offer?: CompanyOffer | null;
  onSaved: (offer: CompanyOffer) => void;
  onCancel: () => void;
  /** Rendered when the backend rejects with company_not_verified. */
  onNotVerified: () => void;
}

function plainOptions(values: readonly string[]): SelectOption[] {
  return values.map((v) => ({ value: v, label: v }));
}

export function OfferForm({ companyId, offer, onSaved, onCancel, onNotVerified }: OfferFormProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const { state, errors, setField, validate } = useOfferForm(
    offer ? offerToForm(offer) : EMPTY_OFFER_FORM,
  );
  const save = useSaveOffer(companyId, offer?.id ?? null);

  const availabilityOptions: SelectOption[] = AVAILABILITY.map((v) => ({
    value: v,
    label: label("availability", v),
  }));

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (!validate()) return;
    save.mutate(
      { payload: formToPayload(state) },
      {
        onSuccess: onSaved,
        onError: (err) => {
          if (isNotVerifiedError(err)) onNotVerified();
        },
      },
    );
  }

  const genericError = save.error && !isNotVerifiedError(save.error) ? save.error.message : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <FormField
        label={t("offers.productText")}
        required
        error={errors.product_text ? t(errors.product_text) : null}
      >
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            value={state.product_text}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setField("product_text", e.target.value)}
          />
        )}
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t("offers.grade")}>
          {({ id }) => (
            <Input id={id} value={state.grade_text} onChange={(e) => setField("grade_text", e.target.value)} />
          )}
        </FormField>
        <FormField label={t("offers.polymerType")}>
          {({ id }) => (
            <Input
              id={id}
              value={state.polymer_type}
              onChange={(e) => setField("polymer_type", e.target.value)}
            />
          )}
        </FormField>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label={t("offers.availability")} required>
          {({ id }) => (
            <Select
              id={id}
              options={availabilityOptions}
              value={state.availability}
              onChange={(e) => setField("availability", e.target.value as typeof state.availability)}
            />
          )}
        </FormField>
        <FormField label={t("offers.qtyAvailable")}>
          {({ id }) => (
            <Input
              id={id}
              inputMode="decimal"
              value={state.qty_available}
              onChange={(e) => setField("qty_available", e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("offers.qtyUnit")} required error={errors.qty_unit ? t(errors.qty_unit) : null}>
          {({ id, invalid }) => (
            <Select
              id={id}
              invalid={invalid}
              options={plainOptions(QTY_UNITS)}
              value={state.qty_unit}
              onChange={(e) => setField("qty_unit", e.target.value)}
            />
          )}
        </FormField>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label={t("offers.price")}>
          {({ id }) => (
            <Input
              id={id}
              inputMode="decimal"
              value={state.price}
              onChange={(e) => setField("price", e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("offers.currency")} required>
          {({ id }) => (
            <Select
              id={id}
              options={plainOptions(CURRENCIES)}
              value={state.currency}
              onChange={(e) => setField("currency", e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("offers.incoterms")} required>
          {({ id }) => (
            <Select
              id={id}
              options={plainOptions(INCOTERMS)}
              value={state.incoterms}
              onChange={(e) => setField("incoterms", e.target.value)}
            />
          )}
        </FormField>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label={t("offers.warehouseCity")}>
          {({ id }) => (
            <Input
              id={id}
              value={state.warehouse_city}
              onChange={(e) => setField("warehouse_city", e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("offers.country")}>
          {({ id }) => (
            <Input id={id} value={state.country} onChange={(e) => setField("country", e.target.value)} />
          )}
        </FormField>
        <FormField label={t("offers.minOrderQty")}>
          {({ id }) => (
            <Input
              id={id}
              inputMode="decimal"
              value={state.min_order_qty}
              onChange={(e) => setField("min_order_qty", e.target.value)}
            />
          )}
        </FormField>
      </div>

      <FormField label={t("offers.description")}>
        {({ id }) => (
          <Textarea
            id={id}
            rows={4}
            value={state.description}
            onChange={(e) => setField("description", e.target.value)}
          />
        )}
      </FormField>

      {genericError ? <Alert tone="danger" title={t("errors.generic")}>{genericError}</Alert> : null}

      <div className="flex justify-end gap-3 border-t border-border pt-4">
        <Button variant="ghost" onClick={onCancel} disabled={save.isPending}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" loading={save.isPending} className="min-w-40">
          {save.isPending ? t("offers.saving") : t("offers.save")}
        </Button>
      </div>
    </form>
  );
}
