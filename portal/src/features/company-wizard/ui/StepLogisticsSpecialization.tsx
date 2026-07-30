import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib";
import { Button } from "@/shared/ui";

import { LOGISTICS_CAPABILITIES, LOGISTICS_CARGO_TYPES } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isLogisticsSpecializationValid } from "../model/validation";

interface StepLogisticsSpecializationProps {
  onNext: () => void;
  onBack: () => void;
}

/** Logistics step 5 — cargo types + company capabilities. */
export function StepLogisticsSpecialization({
  onNext,
  onBack,
}: StepLogisticsSpecializationProps) {
  const { t } = useTranslation();
  const logistics = useWizardDraft((s) => s.logistics);
  const setLogistics = useWizardDraft((s) => s.setLogistics);
  const [submitted, setSubmitted] = useState(false);
  const valid = isLogisticsSpecializationValid(logistics);

  function toggle(list: string[], key: string, field: "cargo_types" | "capabilities"): void {
    const has = list.includes(key);
    setLogistics({
      [field]: has ? list.filter((x) => x !== key) : [...list, key],
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
        <h2 className="text-lg font-semibold text-text">
          {t("wizard.logistics.specialization.title")}
        </h2>
        <p className="mt-1 text-sm text-text-muted">
          {t("wizard.logistics.specialization.subtitle")}
        </p>
      </div>

      {submitted && !valid ? (
        <p className="text-sm text-danger">{t("wizard.logistics.specialization.required")}</p>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.specialization.cargoTitle")}
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {LOGISTICS_CARGO_TYPES.map((cargo) => {
            const active = logistics.cargo_types.includes(cargo);
            return (
              <button
                key={cargo}
                type="button"
                aria-pressed={active}
                onClick={() => toggle(logistics.cargo_types, cargo, "cargo_types")}
                className={cn(
                  "rounded-md border px-3 py-3 text-left text-sm font-medium transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-text"
                    : "border-border bg-surface text-text-muted hover:border-brand-line",
                  cargo === "other_cargo" ? "col-span-2 sm:col-span-1" : null,
                )}
              >
                {t(`wizard.logistics.specialization.cargo.${cargo}`)}
              </button>
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.specialization.capabilitiesTitle")}
        </h3>
        <div className="space-y-2">
          {LOGISTICS_CAPABILITIES.map((cap) => {
            const checked = logistics.capabilities.includes(cap);
            return (
              <button
                key={cap}
                type="button"
                aria-pressed={checked}
                onClick={() => toggle(logistics.capabilities, cap, "capabilities")}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-md border px-3 py-3 text-left transition-colors",
                  checked
                    ? "border-brand bg-brand-soft text-text"
                    : "border-border bg-surface text-text hover:border-brand-line",
                )}
              >
                <span className="text-sm font-medium">
                  {t(`wizard.logistics.specialization.capabilities.${cap}`)}
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
      </section>

      <div className="flex gap-3">
        <Button type="button" variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button type="submit" size="lg" disabled={!valid} className="flex-1" data-testid="wizard-next">
          {t("wizard.logistics.specialization.next")}
        </Button>
      </div>
    </form>
  );
}
