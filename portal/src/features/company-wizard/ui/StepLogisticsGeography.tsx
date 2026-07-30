import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib";
import { Button, MapPinIcon } from "@/shared/ui";

import {
  LOGISTICS_FROM_COUNTRIES,
  LOGISTICS_POPULAR_ROUTES,
  LOGISTICS_TO_COUNTRIES,
} from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isLogisticsGeographyValid } from "../model/validation";

interface StepLogisticsGeographyProps {
  onNext: () => void;
  onBack: () => void;
}

/** Logistics step 4 — from/to countries + popular routes. */
export function StepLogisticsGeography({ onNext, onBack }: StepLogisticsGeographyProps) {
  const { t } = useTranslation();
  const logistics = useWizardDraft((s) => s.logistics);
  const setLogistics = useWizardDraft((s) => s.setLogistics);
  const [submitted, setSubmitted] = useState(false);
  const valid = isLogisticsGeographyValid(logistics);

  function toggleIn(list: string[], key: string, field: "from_countries" | "to_countries" | "popular_routes"): void {
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
        <h2 className="text-lg font-semibold text-text">{t("wizard.logistics.geography.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.logistics.geography.subtitle")}</p>
      </div>

      {submitted && !valid ? (
        <p className="text-sm text-danger">{t("wizard.logistics.geography.required")}</p>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.geography.fromTitle")}
        </h3>
        <div className="flex flex-wrap gap-2">
          {LOGISTICS_FROM_COUNTRIES.map((code) => {
            const active = logistics.from_countries.includes(code);
            return (
              <button
                key={code}
                type="button"
                aria-pressed={active}
                onClick={() => toggleIn(logistics.from_countries, code, "from_countries")}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-text"
                    : "border-border bg-surface text-text-muted hover:border-brand-line",
                )}
              >
                {t(`wizard.logistics.geography.countries.${code}`)}
              </button>
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.geography.toTitle")}
        </h3>
        <div className="flex flex-wrap gap-2">
          {LOGISTICS_TO_COUNTRIES.map((code) => {
            const active = logistics.to_countries.includes(code);
            return (
              <button
                key={code}
                type="button"
                aria-pressed={active}
                onClick={() => toggleIn(logistics.to_countries, code, "to_countries")}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-text"
                    : "border-border bg-surface text-text-muted hover:border-brand-line",
                )}
              >
                {t(`wizard.logistics.geography.countries.${code}`)}
              </button>
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-text">
          {t("wizard.logistics.geography.routesTitle")}
        </h3>
        <div className="space-y-2">
          {LOGISTICS_POPULAR_ROUTES.map((route) => {
            const active = logistics.popular_routes.includes(route);
            return (
              <button
                key={route}
                type="button"
                aria-pressed={active}
                onClick={() => toggleIn(logistics.popular_routes, route, "popular_routes")}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md border px-3 py-3 text-left text-sm transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-text"
                    : "border-border bg-surface text-text hover:border-brand-line",
                )}
              >
                <MapPinIcon size={18} className="shrink-0 text-brand" />
                <span>{t(`wizard.logistics.geography.routes.${route}`)}</span>
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
          {t("wizard.logistics.geography.next")}
        </Button>
      </div>
    </form>
  );
}
