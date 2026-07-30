import { useTranslation } from "react-i18next";

import { Alert, BoxIcon, Button, FileIcon, PlusIcon } from "@/shared/ui";
import { cn } from "@/shared/lib";

interface StepCatalogProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Manufacturer catalog step — UI from the mockup. Product creation / Excel import
 * happen after registration; both tiles and «Далее» simply continue.
 */
export function StepCatalog({ onNext, onBack }: StepCatalogProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.catalog.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.catalog.subtitle")}</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={onNext}
          className={cn(
            "flex flex-col items-center gap-2 rounded-md border border-brand-line bg-brand-soft/40 px-3 py-6 text-center transition-colors hover:bg-brand-soft",
          )}
          data-testid="wizard-catalog-manual"
        >
          <span className="text-brand">
            <PlusIcon size={22} />
          </span>
          <span className="text-sm font-medium text-text">{t("wizard.catalog.addManual")}</span>
        </button>
        <button
          type="button"
          onClick={onNext}
          className={cn(
            "flex flex-col items-center gap-2 rounded-md border border-brand-line bg-brand-soft/40 px-3 py-6 text-center transition-colors hover:bg-brand-soft",
          )}
          data-testid="wizard-catalog-excel"
        >
          <span className="text-brand">
            <FileIcon size={22} />
          </span>
          <span className="text-sm font-medium text-text">{t("wizard.catalog.addExcel")}</span>
          <span className="text-xs text-text-muted">{t("wizard.catalog.excelFormats")}</span>
        </button>
      </div>

      <div>
        <p className="mb-2 text-sm font-medium text-text">
          {t("wizard.catalog.yourProducts", { count: 0 })}
        </p>
        <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border px-4 py-10 text-center">
          <span className="text-text-subtle">
            <BoxIcon size={28} />
          </span>
          <p className="text-sm font-medium text-text">{t("wizard.catalog.emptyTitle")}</p>
          <p className="text-xs text-text-muted">{t("wizard.catalog.emptyBody")}</p>
        </div>
      </div>

      <Alert tone="info" title={t("wizard.catalog.tipTitle")}>
        {t("wizard.catalog.tipBody")}
      </Alert>

      <p className="text-xs text-text-muted">{t("wizard.catalog.deferNote")}</p>

      <div className="flex gap-3">
        <Button type="button" variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button type="button" size="lg" className="flex-1" data-testid="wizard-next" onClick={onNext}>
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
