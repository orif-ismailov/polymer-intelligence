import { useState } from "react";

import { useTranslation } from "react-i18next";

import {
  LOGISTICS_PACKAGING_TYPES,
  useCreateLogisticsRequest,
} from "@/entities/logistics-request";
import {
  LOGISTICS_FROM_COUNTRIES,
  LOGISTICS_TO_COUNTRIES,
} from "@/features/company-wizard/model/constants";
import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import {
  Alert,
  ChevronRightIcon,
  Button,
  Card,
  CardBody,
  FormField,
  Input,
  LockIcon,
  MapPinIcon,
  SendIcon,
  Select,
  Textarea,
  TruckIcon,
} from "@/shared/ui";

interface LogisticsRequestFormProps {
  /** The buyer's acting company. */
  companyId: number;
  onSent: (requestId: number) => void;
}

/**
 * «Быстрая заявка на логистику» — one screen, exactly as the mockup draws it.
 *
 * Not a wizard, and that is a decision rather than a shortcut: the sheet has
 * seven fields in two sections, and the whole promise of the CTA is that asking
 * is quick. `features/factory-rfq` splits across four steps because it collects
 * documents and commercial terms; there is nothing here to page through.
 *
 * No carrier is chosen. The request is BROADCAST — a shipper does not know which
 * of ten firms runs their lane, so they state the job and carriers come to them.
 *
 * Consequently there is no zustand draft either — the draft store in the other
 * flows exists to survive step navigation, and one screen has none.
 */
export function LogisticsRequestForm({ companyId, onSent }: LogisticsRequestFormProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const create = useCreateLogisticsRequest();
  const [touched, setTouched] = useState(false);

  const [form, setForm] = useState({
    cargo_name: "",
    volume: "",
    packaging_type: "",
    special_requirements: "",
    from_country: "",
    from_city: "",
    to_country: "",
    to_city: "",
  });

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));

  const volumeNumber = Number(form.volume.replace(",", "."));
  const volumeOk = form.volume.trim() !== "" && Number.isFinite(volumeNumber) && volumeNumber > 0;
  const cargoOk = form.cargo_name.trim().length > 0;
  const routeOk = form.from_country !== "" && form.to_country !== "";
  const canSubmit = cargoOk && volumeOk && routeOk;

  // Nothing to map by code any more: the only coded refusal this form could get
  // was `self_logistics_request`, and a broadcast has no addressee to be.
  const error = create.error ? t("errors.generic") : null;

  const countryOptions = (codes: readonly string[]) =>
    codes.map((code) => ({
      value: code,
      label:
        code === "other"
          ? t("wizard.logistics.geography.countries.other", { defaultValue: code })
          : countryName(code, lang),
    }));

  function submit(): void {
    setTouched(true);
    if (!canSubmit) return;
    create.mutate(
      {
        company_id: companyId,
        cargo_name: form.cargo_name.trim(),
        volume: String(volumeNumber),
        volume_unit: "MT",
        packaging_type: form.packaging_type || null,
        special_requirements: form.special_requirements.trim() || null,
        from_country: form.from_country,
        from_city: form.from_city.trim() || null,
        to_country: form.to_country,
        to_city: form.to_city.trim() || null,
      },
      { onSuccess: (created) => onSent(created.id) },
    );
  }

  return (
    <div className="space-y-6" data-testid="logistics-request-form">
      <div className="flex items-start gap-3">
        <span className="shrink-0 text-brand">
          <TruckIcon size={32} />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-tight text-text">
            {t("logisticsRequest.heroTitle")}
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-text-muted">
            {t("logisticsRequest.heroBody")}
          </p>
        </div>
      </div>

      {/* ── Информация о грузе ─────────────────────────────────────────── */}
      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-text">{t("logisticsRequest.cargoTitle")}</h3>

        <FormField
          label={t("logisticsRequest.cargoName")}
          required
          error={touched && !cargoOk ? t("logisticsRequest.errors.cargoRequired") : null}
        >
          {({ id, invalid }) => (
            <Input
              id={id}
              value={form.cargo_name}
              invalid={invalid}
              placeholder={t("logisticsRequest.cargoNamePlaceholder")}
              onChange={(e) => set({ cargo_name: e.target.value })}
            />
          )}
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label={t("logisticsRequest.volume")}
            required
            hint={t("logisticsRequest.volumeHint")}
            error={touched && !volumeOk ? t("logisticsRequest.errors.volumeInvalid") : null}
          >
            {({ id, invalid }) => (
              <Input
                id={id}
                inputMode="decimal"
                value={form.volume}
                invalid={invalid}
                placeholder="500"
                onChange={(e) => set({ volume: e.target.value })}
              />
            )}
          </FormField>

          <FormField label={t("logisticsRequest.packaging")}>
            {({ id }) => (
              <Select
                id={id}
                value={form.packaging_type}
                placeholder={t("logisticsRequest.packagingPlaceholder")}
                options={LOGISTICS_PACKAGING_TYPES.map((key) => ({
                  value: key,
                  label: t(`logisticsRequest.packagingOptions.${key}`),
                }))}
                onChange={(e) => set({ packaging_type: e.target.value })}
              />
            )}
          </FormField>
        </div>

        <FormField label={t("logisticsRequest.requirements")}>
          {({ id }) => (
            <Textarea
              id={id}
              rows={2}
              value={form.special_requirements}
              placeholder={t("logisticsRequest.requirementsPlaceholder")}
              onChange={(e) => set({ special_requirements: e.target.value })}
            />
          )}
        </FormField>
      </section>

      {/* ── Маршрут ────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h3 className="text-sm font-semibold text-text">{t("logisticsRequest.routeTitle")}</h3>

        {/* The arrow is decorative chrome between two equal cards, so it is
            hidden from assistive tech — «Откуда» and «Куда» already say it. */}
        <div className="grid items-start gap-3 sm:grid-cols-[1fr_auto_1fr]">
          <Card>
            <CardBody className="space-y-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-text-muted">
                <span className="text-brand">
                  <MapPinIcon size={14} />
                </span>
                {t("logisticsRequest.from")}
              </p>
              <FormField
                label={t("logisticsRequest.country")}
                required
                error={
                  touched && !form.from_country
                    ? t("logisticsRequest.errors.countryRequired")
                    : null
                }
              >
                {({ id, invalid }) => (
                  <Select
                    id={id}
                    value={form.from_country}
                    invalid={invalid}
                    placeholder={t("logisticsRequest.countryPlaceholder")}
                    options={countryOptions(LOGISTICS_FROM_COUNTRIES)}
                    onChange={(e) => set({ from_country: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label={t("logisticsRequest.city")}>
                {({ id }) => (
                  <Input
                    id={id}
                    value={form.from_city}
                    onChange={(e) => set({ from_city: e.target.value })}
                  />
                )}
              </FormField>
            </CardBody>
          </Card>

          <span
            aria-hidden
            className="hidden self-center text-brand sm:block"
          >
            <ChevronRightIcon size={20} />
          </span>

          <Card>
            <CardBody className="space-y-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-text-muted">
                <span className="text-brand">
                  <MapPinIcon size={14} />
                </span>
                {t("logisticsRequest.to")}
              </p>
              <FormField
                label={t("logisticsRequest.country")}
                required
                error={
                  touched && !form.to_country
                    ? t("logisticsRequest.errors.countryRequired")
                    : null
                }
              >
                {({ id, invalid }) => (
                  <Select
                    id={id}
                    value={form.to_country}
                    invalid={invalid}
                    placeholder={t("logisticsRequest.countryPlaceholder")}
                    options={countryOptions(LOGISTICS_TO_COUNTRIES)}
                    onChange={(e) => set({ to_country: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label={t("logisticsRequest.city")}>
                {({ id }) => (
                  <Input
                    id={id}
                    value={form.to_city}
                    onChange={(e) => set({ to_city: e.target.value })}
                  />
                )}
              </FormField>
            </CardBody>
          </Card>
        </div>
      </section>

      {error ? (
        <Alert tone="danger" title={t("errors.generic")} data-testid="logistics-request-error">
          {error}
        </Alert>
      ) : null}

      <Button
        fullWidth
        size="lg"
        loading={create.isPending}
        onClick={submit}
        data-testid="logistics-request-submit"
      >
        <SendIcon size={18} />
        {t("logisticsRequest.submit")}
      </Button>

      <p className="flex items-start justify-center gap-2 text-center text-xs text-text-subtle">
        <span className="mt-0.5 shrink-0">
          <LockIcon size={14} />
        </span>
        {t("logisticsRequest.privacy")}
      </p>
    </div>
  );
}
