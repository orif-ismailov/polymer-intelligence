import { useState } from "react";

import { useTranslation } from "react-i18next";

import { BUSINESS_ROLES } from "@/shared/config";
import { useEnumLabels } from "@/shared/i18n";
import { Alert, Button, Checkbox } from "@/shared/ui";

import { useWizardDraft } from "../model/draftStore";
import { isRolesValid } from "../model/validation";

interface StepRolesProps {
  onNext: () => void;
  onBack: () => void;
}

export function StepRoles({ onNext, onBack }: StepRolesProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const roles = useWizardDraft((s) => s.roles);
  const toggleRole = useWizardDraft((s) => s.toggleRole);
  const [touched, setTouched] = useState(false);

  const valid = isRolesValid(roles);

  function handleNext(): void {
    setTouched(true);
    if (valid) onNext();
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-text">{t("wizard.roles.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.roles.subtitle")}</p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {BUSINESS_ROLES.map((role) => (
          <Checkbox
            key={role}
            id={`role-${role}`}
            label={label("businessRole", role)}
            checked={roles.includes(role)}
            onChange={() => toggleRole(role)}
          />
        ))}
      </div>

      {touched && !valid ? <Alert tone="warning" title={t("wizard.roles.atLeastOne")} /> : null}

      <div className="flex justify-between border-t border-border pt-4">
        <Button variant="ghost" onClick={onBack}>
          {t("common.back")}
        </Button>
        <Button onClick={handleNext} disabled={!valid} className="min-w-40">
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
