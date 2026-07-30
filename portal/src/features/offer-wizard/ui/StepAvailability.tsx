import { useState } from "react";

import { useTranslation } from "react-i18next";

import { CURRENCIES, QTY_UNITS } from "@/shared/config";
import {
  BoxIcon,
  ChoiceTile,
  ClockIcon,
  FormField,
  InfoIcon,
  Input,
  Select,
  StepPanel,
} from "@/shared/ui";
import type { SelectOption } from "@/shared/ui";

import {
  COUNTED_STEPS,
  DISPATCH_BANDS,
  OTHER_OPTION,
  STEP_AVAILABILITY,
  WAREHOUSE_LOCATIONS,
  type DispatchBandId,
} from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { isAvailabilityValid } from "../model/validation";
import { StepNav } from "./StepNav";

interface StepAvailabilityProps {
  onNext: () => void;
  onBack: () => void;
}

function plain(values: readonly string[]): SelectOption[] {
  return values.map((value) => ({ value, label: value }));
}

/** Sheet 3 — «Наличие / Под заказ». */
export function StepAvailability({ onNext, onBack }: StepAvailabilityProps) {
  const { t } = useTranslation();
  const draft = useOfferDraft((s) => s.draft);
  const setField = useOfferDraft((s) => s.setField);
  const [touched, setTouched] = useState(false);

  const onOrder = draft.availability === "on_order";
  const valid = isAvailabilityValid(draft);

  const warehouseOptions: SelectOption[] = [
    ...WAREHOUSE_LOCATIONS.map((city) => ({
      value: city,
      // The stored value is the city itself, so a missing translation still
      // renders the thing that will be saved rather than a raw key.
      label: t(`offerWizard.availability.cities.${city}`, city),
    })),
    { value: OTHER_OPTION, label: t("offerWizard.availability.cityOther") },
  ];

  const dispatchOptions: SelectOption[] = DISPATCH_BANDS.map((band) => ({
    value: band.id,
    label: t(`offerWizard.availability.dispatch.${band.id}`),
  }));

  function handleNext(): void {
    setTouched(true);
    if (valid) onNext();
  }

  return (
    <StepPanel
      step={STEP_AVAILABILITY}
      title={t("offerWizard.availability.title")}
      counter={t("offerWizard.stepOf", { current: STEP_AVAILABILITY, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-3"
    >
      <div className="space-y-4">
        <div>
          <p className="mb-1.5 text-sm font-medium text-text">
            {t("offerWizard.availability.kind")}
            <span className="ms-1 text-danger">*</span>
          </p>
          <div className="grid grid-cols-2 gap-3">
            <ChoiceTile
              name="offer-availability"
              value="in_stock"
              tone="gold"
              checked={!onOrder}
              onChange={() => setField("availability", "in_stock")}
              icon={<BoxIcon size={22} />}
              title={t("availability.in_stock")}
              description={t("offerWizard.availability.inStockHint")}
              data-testid="offer-wizard-in-stock"
            />
            <ChoiceTile
              name="offer-availability"
              value="on_order"
              tone="gold"
              checked={onOrder}
              onChange={() => setField("availability", "on_order")}
              icon={<ClockIcon size={22} />}
              title={t("availability.on_order")}
              description={t("offerWizard.availability.onOrderHint")}
              data-testid="offer-wizard-on-order"
            />
          </div>
        </div>

        <p className="flex items-start gap-2 rounded-md border border-border bg-surface-inset px-3 py-2.5 text-xs leading-relaxed text-text-muted">
          <span className="mt-px shrink-0 text-info">
            <InfoIcon size={14} />
          </span>
          {onOrder
            ? t("offerWizard.availability.onOrderNote")
            : t("offerWizard.availability.inStockNote")}
        </p>

        {/* «Под заказ» has no stock on hand and no unit price — the card says
            "по запросу", so asking for either would be asking for a fiction. */}
        {onOrder ? null : (
          <>
            <div className="grid grid-cols-[1fr_auto] gap-3">
              <FormField
                label={t("offerWizard.availability.qty")}
                required
                error={
                  touched && draft.qty.trim() === "" ? t("offerWizard.availability.qtyRequired") : null
                }
              >
                {({ id, invalid, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={draft.qty}
                    invalid={invalid}
                    aria-describedby={describedBy}
                    placeholder="500"
                    onChange={(e) => setField("qty", e.target.value)}
                    data-testid="offer-wizard-qty"
                  />
                )}
              </FormField>
              <FormField label={t("offers.qtyUnit")} className="w-28">
                {({ id }) => (
                  <Select
                    id={id}
                    options={plain(QTY_UNITS)}
                    value={draft.qtyUnit}
                    onChange={(e) => setField("qtyUnit", e.target.value)}
                  />
                )}
              </FormField>
            </div>

            <div className="grid grid-cols-[1fr_auto] gap-3">
              <FormField
                label={t("offerWizard.availability.price")}
                required
                error={
                  touched && draft.price.trim() === ""
                    ? t("offerWizard.availability.priceRequired")
                    : null
                }
              >
                {({ id, invalid, describedBy }) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    value={draft.price}
                    invalid={invalid}
                    aria-describedby={describedBy}
                    placeholder="1020"
                    onChange={(e) => setField("price", e.target.value)}
                    data-testid="offer-wizard-price"
                  />
                )}
              </FormField>
              <FormField label={t("offers.currency")} className="w-28">
                {({ id }) => (
                  <Select
                    id={id}
                    options={plain(CURRENCIES)}
                    value={draft.currency}
                    onChange={(e) => setField("currency", e.target.value)}
                  />
                )}
              </FormField>
            </div>
          </>
        )}

        <FormField label={t("offerWizard.availability.warehouse")}>
          {({ id }) => (
            <Select
              id={id}
              options={warehouseOptions}
              value={draft.warehouseChoice}
              onChange={(e) => setField("warehouseChoice", e.target.value)}
            />
          )}
        </FormField>

        {draft.warehouseChoice === OTHER_OPTION ? (
          <FormField
            label={t("offerWizard.availability.warehouseManual")}
            required
            error={
              touched && draft.warehouseOther.trim() === ""
                ? t("offerWizard.availability.warehouseRequired")
                : null
            }
          >
            {({ id, invalid, describedBy }) => (
              <Input
                id={id}
                value={draft.warehouseOther}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setField("warehouseOther", e.target.value)}
              />
            )}
          </FormField>
        ) : null}

        <FormField label={t("offerWizard.availability.dispatch.label")}>
          {({ id }) => (
            <Select
              id={id}
              options={dispatchOptions}
              value={draft.dispatchBand}
              onChange={(e) => setField("dispatchBand", e.target.value as DispatchBandId)}
            />
          )}
        </FormField>
      </div>

      <StepNav onNext={handleNext} onBack={onBack} />
    </StepPanel>
  );
}
