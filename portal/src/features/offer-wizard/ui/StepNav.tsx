import { useTranslation } from "react-i18next";

import { Button, ChevronRightIcon } from "@/shared/ui";

interface StepNavProps {
  onNext: () => void;
  /** Omitted on the first sheet, which has nowhere to go back to inside the flow. */
  onBack?: () => void;
  disabled?: boolean;
  nextLabel?: string;
  "data-testid"?: string;
}

/**
 * The foot of every collecting sheet: the mockup's full-width green «Далее →»,
 * with «← Назад» beside it from sheet 2 on.
 *
 * `size="lg"` and `fullWidth` on sheet 1 are not decoration — the mockup's first
 * sheet has a single edge-to-edge CTA, and every later one splits the row.
 */
export function StepNav({
  onNext,
  onBack,
  disabled = false,
  nextLabel,
  "data-testid": testId,
}: StepNavProps) {
  const { t } = useTranslation();
  return (
    <div className="mt-6 flex gap-3">
      {onBack ? (
        <Button variant="ghost" size="lg" onClick={onBack} className="min-w-24">
          {t("common.back")}
        </Button>
      ) : null}
      <Button
        size="lg"
        onClick={onNext}
        disabled={disabled}
        className="flex-1"
        data-testid={testId ?? "offer-wizard-next"}
      >
        {nextLabel ?? t("common.next")}
        <ChevronRightIcon size={16} />
      </Button>
    </div>
  );
}
