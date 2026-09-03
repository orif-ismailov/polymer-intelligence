import { useTranslation } from "react-i18next";

import { RadioCard, ShieldCheckIcon, StoreIcon } from "@/shared/ui";

import {
  COUNTED_STEPS,
  STEP_COMM,
  VISIBILITY_OPTIONS,
  type VisibilityOption,
} from "../model/constants";
import { useRequestDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepCommProps {
  onNext: () => void;
  onBack: () => void;
}

const VISIBILITY_ICON = {
  verified: <ShieldCheckIcon size={18} />,
  all: <StoreIcon size={18} />,
} as const;

/**
 * Sheet 4 — «Кто увидит тендер»: the one choice on this sheet that the API
 * acts on. It used to also ask how offers should arrive (email / Telegram),
 * which nothing ever sent, and both answers were folded into `comment`.
 */
export function StepComm({ onNext, onBack }: StepCommProps) {
  const { t } = useTranslation();
  const draft = useRequestDraft((s) => s.draft);
  const setField = useRequestDraft((s) => s.setField);

  return (
    <div className="space-y-6" data-testid="request-wizard-step-4">
      <header>
        <p className="num text-xs text-text-muted">
          {t("requestWizard.stepOf", { current: STEP_COMM, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">
          {t("requestWizard.comm.title")}
        </h2>
      </header>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-medium text-text">
          {t("requestWizard.comm.visibilityLabel")}
        </legend>
        {VISIBILITY_OPTIONS.map((opt) => (
          <RadioCard
            key={opt}
            name="visibility"
            value={opt}
            checked={draft.visibility === opt}
            onChange={(v) => setField("visibility", v as VisibilityOption)}
            title={t(`requestWizard.comm.visibility.${opt}.title`)}
            description={t(`requestWizard.comm.visibility.${opt}.body`)}
            icon={VISIBILITY_ICON[opt]}
            data-testid={`request-wizard-visibility-${opt}`}
          />
        ))}
      </fieldset>

      <p className="text-sm leading-relaxed text-text-muted">
        {t("requestWizard.comm.contactsNote")}
      </p>

      <StepNav onNext={onNext} onBack={onBack} />
    </div>
  );
}
