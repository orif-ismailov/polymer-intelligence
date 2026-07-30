import { useTranslation } from "react-i18next";

import { Button, ChevronRightIcon } from "@/shared/ui";

interface StepNavProps {
  onNext: () => void;
  onBack?: () => void;
  disabled?: boolean;
  nextLabel?: string;
  /** Gold CTA on the preview sheet — mockup paints Publish amber. */
  variant?: "primary" | "gold";
  loading?: boolean;
  "data-testid"?: string;
}

/**
 * Foot of every sheet: full-width green «Далее →». From sheet 2 on, «← Назад»
 * sits beside it. The preview sheet reuses this with `variant="gold"` and no
 * chevron so it reads as the Publish action the mockup shows.
 */
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
  const isPublish = variant === "gold";
  return (
    <div className="mt-6 flex flex-col gap-3">
      <div className="flex gap-3">
        {onBack && !isPublish ? (
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
          fullWidth={!onBack || isPublish}
          data-testid={testId ?? "request-wizard-next"}
        >
          {nextLabel ?? t("common.next")}
          {isPublish ? null : <ChevronRightIcon size={16} />}
        </Button>
      </div>
    </div>
  );
}
