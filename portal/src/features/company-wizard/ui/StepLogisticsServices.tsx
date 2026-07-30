import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib";
import { Button } from "@/shared/ui";

import { LOGISTICS_SERVICE_OPTIONS } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isLogisticsServicesValid } from "../model/validation";

interface StepLogisticsServicesProps {
  onNext: () => void;
  onBack: () => void;
}

/** Logistics step 3 — services checklist from logist_reg_flow.jpeg. */
export function StepLogisticsServices({ onNext, onBack }: StepLogisticsServicesProps) {
  const { t } = useTranslation();
  const logistics = useWizardDraft((s) => s.logistics);
  const setLogistics = useWizardDraft((s) => s.setLogistics);
  const [submitted, setSubmitted] = useState(false);
  const valid = isLogisticsServicesValid(logistics);

  function toggleService(service: string): void {
    const has = logistics.services.includes(service);
    setLogistics({
      services: has
        ? logistics.services.filter((s) => s !== service)
        : [...logistics.services, service],
    });
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (valid) onNext();
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit} noValidate>
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.logistics.services.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.logistics.services.subtitle")}</p>
      </div>

      {submitted && !valid ? (
        <p className="text-sm text-danger">{t("wizard.logistics.services.required")}</p>
      ) : null}

      <div className="space-y-2" role="group" aria-label={t("wizard.logistics.services.title")}>
        {LOGISTICS_SERVICE_OPTIONS.map((service) => {
          const checked = logistics.services.includes(service);
          return (
            <button
              key={service}
              type="button"
              aria-pressed={checked}
              onClick={() => toggleService(service)}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-md border px-3 py-3 text-left transition-colors",
                checked
                  ? "border-brand bg-brand-soft text-text"
                  : "border-border bg-surface text-text hover:border-brand-line",
              )}
            >
              <span className="text-sm font-medium">
                {t(`wizard.logistics.services.options.${service}`)}
              </span>
              <span
                aria-hidden
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                  checked
                    ? "border-brand bg-brand text-brand-fg"
                    : "border-border bg-surface text-transparent",
                )}
              >
                ✓
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex gap-3">
        <Button type="button" variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button type="submit" size="lg" disabled={!valid} className="flex-1" data-testid="wizard-next">
          {t("wizard.logistics.services.next")}
        </Button>
      </div>
    </form>
  );
}
