import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { useTechOfferAction, type TechOffer } from "@/entities/tech-request";
import { useTechFacets } from "@/entities/technologist";
import { Alert, Button, FormField, Input, Select, Textarea, ToggleChips } from "@/shared/ui";

interface TechOfferFormProps {
  requestId: number;
  /** The expert's current offer — present means «Изменить», absent «Отправить». */
  existing: TechOffer | null;
  /** The request's own format, the sensible default for a first offer. */
  defaultFormat: string;
  onDone?: () => void;
}

/**
 * The expert's proposal: what they will do, for how much, in how many days.
 * The brief's «2 дня консультации, 1 день на производстве · $1 500 · 3 days».
 */
export function TechOfferForm({ requestId, existing, defaultFormat, onDone }: TechOfferFormProps) {
  const { t } = useTranslation();
  const facets = useTechFacets();
  const action = useTechOfferAction(requestId);
  const [scope, setScope] = useState(existing?.scope ?? "");
  const [price, setPrice] = useState(existing?.price ?? "");
  const [currency, setCurrency] = useState(existing?.currency ?? "USD");
  const [days, setDays] = useState(existing ? String(existing.duration_days) : "");
  const [format, setFormat] = useState(existing?.work_format ?? defaultFormat);
  const [submitted, setSubmitted] = useState(false);

  const priceValid = Number(price) > 0;
  const daysValid = Number.isInteger(Number(days)) && Number(days) > 0;
  const valid = scope.trim() !== "" && priceValid && daysValid && format !== "";
  const required = t("techRequest.form.required");

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (!valid) return;
    action.mutate(
      {
        action: existing ? "update" : "submit",
        payload: {
          scope: scope.trim(),
          price: price.replace(",", "."),
          currency,
          duration_days: Number(days),
          work_format: format,
        },
      },
      { onSuccess: () => onDone?.() },
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4" data-testid="tech-offer-form">
      <FormField label={t("techOffer.scope")} required error={submitted && !scope.trim() ? required : null}>
        {({ id, invalid }) => (
          <Textarea
            id={id}
            rows={4}
            aria-invalid={invalid || undefined}
            value={scope}
            placeholder={t("techOffer.scopePlaceholder")}
            onChange={(e) => setScope(e.target.value)}
          />
        )}
      </FormField>
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_7rem_minmax(0,1fr)]">
        <FormField label={t("techOffer.price")} required error={submitted && !priceValid ? required : null}>
          {({ id, invalid }) => (
            <Input
              id={id}
              invalid={invalid}
              inputMode="decimal"
              className="num"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("techOffer.currency")}>
          {({ id }) => (
            <Select
              id={id}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              options={(facets.data?.currencies ?? ["USD"]).map((c) => ({ value: c, label: c }))}
            />
          )}
        </FormField>
        <FormField label={t("techOffer.days")} required error={submitted && !daysValid ? required : null}>
          {({ id, invalid }) => (
            <Input
              id={id}
              invalid={invalid}
              inputMode="numeric"
              className="num"
              value={days}
              onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))}
            />
          )}
        </FormField>
      </div>
      <FormField label={t("techRequest.form.workFormat")} required>
        {() => (
          <ToggleChips
            label={t("techRequest.form.workFormat")}
            single
            options={facets.data?.request_formats ?? []}
            value={format ? [format] : []}
            onChange={(v) => setFormat(v[0] ?? "")}
            renderLabel={(o) => t(`technologists.format.${o}`)}
          />
        )}
      </FormField>
      {action.isError ? (
        <Alert
          tone="danger"
          title={action.error.status === 409 ? t("techOffer.conflict") : t("errors.generic")}
        />
      ) : null}
      <Button type="submit" size="lg" fullWidth loading={action.isPending}>
        {existing ? t("techOffer.update") : t("techOffer.submit")}
      </Button>
    </form>
  );
}
