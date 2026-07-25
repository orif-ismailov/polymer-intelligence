import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { companyApi, useActiveCompanyStore } from "@/entities/company";
import { EimzoSignDialog } from "@/features/eimzo-sign";
import { ApiError } from "@/shared/api";
import { JURISDICTIONS } from "@/shared/config";
import { Alert, Button, FormField, Input, Select } from "@/shared/ui";

import { useWizardDraft } from "../model/draftStore";
import { useEnumOptions } from "../model/useEnumOptions";
import { isTaxIdValid } from "../model/validation";

interface StepIdentityProps {
  onNext: () => void;
}

export function StepIdentity({ onNext }: StepIdentityProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const identity = useWizardDraft((s) => s.identity);
  const setIdentity = useWizardDraft((s) => s.setIdentity);
  const setActiveCompany = useActiveCompanyStore((s) => s.setActiveCompany);
  const jurisdictionOptions = useEnumOptions("jurisdiction", JURISDICTIONS);
  const [touched, setTouched] = useState(false);

  // E-IMZO onboarding: the company is created up-front so it can be signed.
  const [eimzoCompanyId, setEimzoCompanyId] = useState<number | null>(null);
  const [eimzoOpen, setEimzoOpen] = useState(false);
  const [eimzoBusy, setEimzoBusy] = useState(false);
  const [eimzoError, setEimzoError] = useState<string | null>(null);

  const taxOk = isTaxIdValid(identity);
  const showTaxError = touched && !taxOk;

  function handleNext(): void {
    setTouched(true);
    if (taxOk) onNext();
  }

  async function handleEimzo(): Promise<void> {
    setTouched(true);
    if (!taxOk) return;
    setEimzoError(null);
    let companyId = eimzoCompanyId;
    if (companyId == null) {
      setEimzoBusy(true);
      try {
        const created = await companyApi.create({
          jurisdiction: identity.jurisdiction,
          tax_id: identity.tax_id.trim(),
        });
        companyId = created.id;
        setEimzoCompanyId(companyId);
        setActiveCompany(companyId);
      } catch (err) {
        setEimzoError(
          err instanceof ApiError && err.status === 409
            ? t("wizard.errors.duplicate")
            : t("wizard.errors.createFailed"),
        );
        setEimzoBusy(false);
        return;
      }
      setEimzoBusy(false);
    }
    setEimzoOpen(true);
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.identity.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.identity.subtitle")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t("companies.jurisdiction")} required>
          {({ id }) => (
            <Select
              id={id}
              options={jurisdictionOptions}
              value={identity.jurisdiction}
              onChange={(e) => setIdentity({ jurisdiction: e.target.value })}
            />
          )}
        </FormField>

        <FormField
          label={t("companies.taxId")}
          required
          hint={t("wizard.identity.taxIdHint")}
          error={showTaxError ? t("wizard.identity.taxIdInvalid") : null}
        >
          {({ id, invalid, describedBy }) => (
            <Input
              id={id}
              inputMode="numeric"
              value={identity.tax_id}
              invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => setIdentity({ tax_id: e.target.value.replace(/\s+/g, "") })}
              onBlur={() => setTouched(true)}
            />
          )}
        </FormField>
      </div>

      <FormField label={t("companies.legalName")}>
        {({ id }) => (
          <Input
            id={id}
            value={identity.legal_name}
            onChange={(e) => setIdentity({ legal_name: e.target.value })}
          />
        )}
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t("company.legalForm")}>
          {({ id }) => (
            <Input
              id={id}
              placeholder="ООО / ЧП / АО"
              value={identity.legal_form}
              onChange={(e) => setIdentity({ legal_form: e.target.value })}
            />
          )}
        </FormField>

        <FormField label={t("company.director")}>
          {({ id }) => (
            <Input
              id={id}
              value={identity.director_name}
              onChange={(e) => setIdentity({ director_name: e.target.value })}
            />
          )}
        </FormField>
      </div>

      <FormField label={t("company.legalAddress")}>
        {({ id }) => (
          <Input
            id={id}
            value={identity.legal_address}
            onChange={(e) => setIdentity({ legal_address: e.target.value })}
          />
        )}
      </FormField>

      <div className="rounded-md border border-dashed border-border bg-surface-2/40 p-4">
        <p className="text-sm font-medium text-text">{t("wizard.identity.eimzoLead")}</p>
        <p className="mt-1 text-xs text-text-muted">{t("wizard.identity.eimzoHint")}</p>
        {eimzoError ? (
          <Alert tone="danger" className="mt-3">
            {eimzoError}
          </Alert>
        ) : null}
        <Button
          variant="secondary"
          className="mt-3"
          disabled={!taxOk || eimzoBusy}
          onClick={() => void handleEimzo()}
          data-testid="wizard-eimzo"
        >
          {eimzoBusy ? t("common.loading") : t("wizard.identity.eimzo")}
        </Button>
      </div>

      <div className="flex justify-end border-t border-border pt-4">
        <Button onClick={handleNext} disabled={!taxOk} className="sm:min-w-40">
          {t("common.next")}
        </Button>
      </div>

      <EimzoSignDialog
        open={eimzoOpen}
        companyId={eimzoOpen ? eimzoCompanyId : null}
        onClose={() => setEimzoOpen(false)}
        onConfirmed={() => {
          setEimzoOpen(false);
          if (eimzoCompanyId != null) {
            void navigate(`/companies/${eimzoCompanyId}/verification`);
          }
        }}
      />
    </div>
  );
}
