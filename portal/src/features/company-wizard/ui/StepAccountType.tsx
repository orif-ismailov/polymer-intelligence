import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { companyApi, companyKeys } from "@/entities/company";
import { Alert, Button, RadioCard } from "@/shared/ui";

import { ACCOUNT_TYPES } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { isAccountTypeValid } from "../model/validation";
import { AccountTypeGlyph } from "./wizardGlyphs";
import { EimzoSignPanel } from "./EimzoSignPanel";

interface StepAccountTypeProps {
  onNext: () => void;
}

/**
 * Step 1 — «Выберите тип аккаунта» plus «Электронная подпись».
 *
 * The two live on one screen because they answer the same question from opposite
 * ends: the cards declare what this company does, and the E-IMZO key proves who
 * it is. Signing here also short-circuits the next screen — the certificate's
 * subject fills the requisites in.
 */
export function StepAccountType({ onNext }: StepAccountTypeProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const accountType = useWizardDraft((s) => s.accountType);
  const setAccountType = useWizardDraft((s) => s.setAccountType);
  const hydrateFromCompany = useWizardDraft((s) => s.hydrateFromCompany);
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

      <div className="border-t border-border pt-6">
        <EimzoSignPanel
          onSigned={(registration) => {
            // `eimzo_service.verify` writes the certificate's requisites onto the
            // company and freezes them, so the filled-in values come from a
            // refetch — never from `holder_masked`, which is a display string.
            void companyApi.get(registration.company_id).then((company) => {
              qc.setQueryData(companyKeys.detail(company.id), company);
              hydrateFromCompany(company);
            });
          }}
        />
      </div>

      <Button fullWidth size="lg" onClick={handleNext} disabled={!valid} data-testid="wizard-next">
        {t("common.next")}
      </Button>
    </div>
  );
}
