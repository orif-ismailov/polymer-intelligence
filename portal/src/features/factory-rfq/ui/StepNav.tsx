import { useTranslation } from "react-i18next";

import { Button, ChevronRightIcon } from "@/shared/ui";

interface StepNavProps {
  onNext: () => void;
  onBack?: () => void;
  disabled?: boolean;
  nextLabel?: string;
  /** Gold CTA on the contact sheet — mirrors the request wizard's Publish. */
  variant?: "primary" | "gold";
  loading?: boolean;
  "data-testid"?: string;
}

/** Foot of every sheet: full-width «Далее →», with «Назад» from sheet 2 on. */
export function StepNav({
  onNext,
  onBack,
  disabled = false,
  nextLabel,
  variant = "primary",
  loading = false,
  "data-testid": testId,
}: StepNavProps) {
  const { t } = useTranslation();
  const isSubmit = variant === "gold";
  return (
    <div className="mt-6 flex flex-col gap-3">
      <div className="flex gap-3">
        {onBack && !isSubmit ? (
          <Button variant="ghost" size="lg" onClick={onBack} className="min-w-24">
            {t("common.back")}
          </Button>
        ) : null}
        <Button
          size="lg"
          variant={variant}
          onClick={onNext}
          disabled={disabled}
          loading={loading}
          className="flex-1"
          fullWidth={!onBack || isSubmit}
          data-testid={testId ?? "factory-rfq-next"}
        >
          {nextLabel ?? t("common.next")}
          {isSubmit ? null : <ChevronRightIcon size={16} />}
        </Button>
      </div>
    </div>
  );
}
