import { useState } from "react";

import { useTranslation } from "react-i18next";

import { CURRENCIES } from "@/shared/config";
import { Alert, Button, FormField, Input, Select } from "@/shared/ui";

import { useWizardDraft } from "../model/draftStore";
import { useEnumOptions } from "../model/useEnumOptions";
import { isBankValid, isMfoValid } from "../model/validation";

interface StepBankProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Step 3 — «Банковский счёт». Not one of the mockup's four sheets, but the
 * verification case's `bank_requisites` check reads what it collects, so it keeps
 * its place in the flow wearing the same chrome as the sheets around it.
 */
export function StepBank({ onNext, onBack }: StepBankProps) {
  const { t } = useTranslation();
  const bank = useWizardDraft((s) => s.bank);
  const setBank = useWizardDraft((s) => s.setBank);
  const currencyOptions = useEnumOptions("currency", CURRENCIES);
  const [touched, setTouched] = useState(false);

  const mfoOk = isMfoValid(bank.bank_mfo);
  const accountOk = bank.account_number.trim().length > 0;
  const valid = isBankValid({ ...bank, enabled: true });

  function proceed(withAccount: boolean): void {
    if (!withAccount) {
      setBank({ enabled: false });
      onNext();
      return;
    }
    setTouched(true);
    setBank({ enabled: true });
    if (valid) onNext();
  }

  const currencyValue = currencyOptions.some((o) => o.value === bank.currency)
    ? bank.currency
    : currencyOptions[0]?.value ?? "";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.bank.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.bank.subtitle")}</p>
      </div>

      <div className="space-y-5">
        <FormField
          label={t("company.bankMfo")}
          hint={t("wizard.bank.mfoHint")}
          error={touched && !mfoOk ? t("wizard.bank.mfoInvalid") : null}
        >
          {({ id, invalid, describedBy }) => (
            <Input
              id={id}
              inputMode="numeric"
              maxLength={5}
              value={bank.bank_mfo}
              invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setBank({ bank_mfo: e.target.value.replace(/\D+/g, "").slice(0, 5) })}
            />
          )}
        </FormField>

        <FormField
          label={t("company.accountNumber")}
          error={touched && !accountOk ? t("wizard.bank.accountInvalid") : null}
        >
          {({ id, invalid, describedBy }) => (
            <Input
              id={id}
              inputMode="numeric"
              value={bank.account_number}
              invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setBank({ account_number: e.target.value.replace(/\s+/g, "") })}
            />
          )}
        </FormField>

        <FormField label={t("company.bankName")}>
          {({ id }) => (
            <Input
              id={id}
              value={bank.bank_name}
              onChange={(e) => setBank({ bank_name: e.target.value })}
            />
          )}
        </FormField>

        <FormField label={t("company.currency")}>
          {({ id }) => (
            <Select
              id={id}
              options={currencyOptions}
              value={currencyValue}
              onChange={(e) => setBank({ currency: e.target.value })}
            />
          )}
        </FormField>
      </div>

      <Alert tone="info">{t("wizard.bank.skipHint")}</Alert>

      <div className="space-y-3">
        <Button
          fullWidth
          size="lg"
          onClick={() => proceed(true)}
          data-testid="wizard-next"
        >
          {t("common.next")}
        </Button>
        <div className="flex gap-3">
          <Button variant="ghost" size="lg" onClick={onBack} className="min-w-24">
            {t("common.back")}
          </Button>
          <Button variant="outline" size="lg" onClick={() => proceed(false)} className="flex-1">
            {t("common.skip")}
          </Button>
        </div>
      </div>
    </div>
  );
}
