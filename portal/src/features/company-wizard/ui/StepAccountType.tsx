import { useState } from "react";

import { useTranslation } from "react-i18next";

import { Alert, Button, RadioCard } from "@/shared/ui";

import { ACCOUNT_TYPES } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isAccountTypeValid } from "../model/validation";
import { AccountTypeGlyph } from "./wizardGlyphs";

interface StepAccountTypeProps {
  onNext: () => void;
}

/**
 * Step 1 — «Выберите тип аккаунта», and nothing else.
 *
 * The E-IMZO key used to be presented here too, on the theory that proving who
 * you are and declaring what you do are the same question from opposite ends.
 * In practice it made the first screen ask two things at once, and the panel
 * carried a method choice with two dead options plus a PIN box the module never
 * read. Identity now belongs to step 2, beside the ИНН it resolves — see
 * `CompanyCertificateSelect`.
 */
export function StepAccountType({ onNext }: StepAccountTypeProps) {
  const { t } = useTranslation();
  const accountType = useWizardDraft((s) => s.accountType);
  const setAccountType = useWizardDraft((s) => s.setAccountType);
  const [touched, setTouched] = useState(false);

  const valid = isAccountTypeValid(accountType);

  function handleNext(): void {
    setTouched(true);
    if (valid) onNext();
  }

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-text">{t("wizard.accountType.title")}</h2>
          <p className="mt-1 text-sm text-text-muted">{t("wizard.accountType.subtitle")}</p>
        </div>

        <div className="space-y-3" role="radiogroup" aria-label={t("wizard.accountType.title")}>
          {ACCOUNT_TYPES.map((spec) => (
            <RadioCard
              key={spec.id}
              name="account-type"
              value={spec.id}
              checked={accountType === spec.id}
              onChange={setAccountType}
              title={t(`wizard.accountType.options.${spec.id}.title`)}
              description={t(`wizard.accountType.options.${spec.id}.description`)}
              icon={<AccountTypeGlyph type={spec.id} />}
              data-testid={`account-type-${spec.id}`}
            />
          ))}
        </div>

        {touched && !valid ? <Alert tone="warning" title={t("wizard.accountType.required")} /> : null}
      </section>

      <Button fullWidth size="lg" onClick={handleNext} disabled={!valid} data-testid="wizard-next">
        {t("common.next")}
      </Button>
    </div>
  );
}
