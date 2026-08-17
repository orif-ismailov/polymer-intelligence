import { useTranslation } from "react-i18next";

import { Alert, Spinner } from "@/shared/ui";

import { useRegistryPrefill } from "../model/useRegistryPrefill";

/**
 * One line telling the applicant where the filled-in fields came from.
 *
 * Shown on both the details and the bank step — the same lookup fills both, and
 * a person who sees their bank account appear by itself deserves to be told why
 * on the screen it appeared on.
 *
 * Absence and outage are stated plainly rather than hidden: a form that quietly
 * did not prefill looks broken, and one that says "type it in" does not.
 */
export function RegistryPrefillNotice() {
  const { t } = useTranslation();
  const { status, registryStatusText } = useRegistryPrefill();

  if (status === "idle") return null;

  if (status === "loading") {
    return (
      <div
        className="flex items-center gap-2 text-sm text-text-muted"
        data-testid="registry-prefill-loading"
      >
        <Spinner />
        {t("wizard.registry.loading")}
      </div>
    );
  }

  if (status === "filled") {
    return (
      <Alert tone="info" title={t("wizard.registry.filledTitle")} data-testid="registry-prefill-filled">
        {t("wizard.registry.filledBody")}
        {registryStatusText ? ` ${t("wizard.registry.state", { state: registryStatusText })}` : ""}
      </Alert>
    );
  }

  if (status === "not_found") {
    return (
      <Alert tone="warning" data-testid="registry-prefill-not-found">
        {t("wizard.registry.notFound")}
      </Alert>
    );
  }

  // `info`, not `warning`: an unreachable registry is our problem, not a defect
  // in what the applicant is doing, and nothing about the form has changed.
  return (
    <Alert tone="info" data-testid="registry-prefill-unavailable">
      {t("wizard.registry.unavailable")}
    </Alert>
  );
}
