import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";

import { companyRegistrationSigner, useEimzoSign } from "@/features/eimzo-sign";
import type { EimzoRegistration } from "@/features/eimzo-sign";
import {
  Alert,
  Button,
  Card,
  CardBody,
  FormField,
  IconTile,
  PasswordInput,
  UsbIcon,
  ShieldIcon,
  Tabs,
} from "@/shared/ui";
import type { TabItem } from "@/shared/ui";

import { EIMZO_AVAILABLE_METHOD, EIMZO_METHODS } from "../model/constants";
import type { EimzoMethod } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { UsbTokenArt } from "./UsbTokenArt";

const INSTRUCTION_STEPS = [1, 2, 3] as const;

interface EimzoSignPanelProps {
  /** Fired once the signature lands, with the company it created. */
  onSigned: (registration: EimzoRegistration) => void;
}

/**
 * «Электронная подпись» — the signing block on registration step 1.
 *
 * Signing first is what makes the rest of the wizard short: the certificate
 * subject carries the organisation's STIR and name, so a signed company arrives
 * at «Основная информация» already filled in and frozen. Skipping it is fine —
 * «Далее» carries on to the manual form.
 */
export function EimzoSignPanel({ onSigned }: EimzoSignPanelProps) {
  const { t } = useTranslation();
  const jurisdiction = useWizardDraft((s) => s.identity.jurisdiction);
  const adoptCompany = useWizardDraft((s) => s.adoptCompany);

  const [method, setMethod] = useState<EimzoMethod>(EIMZO_AVAILABLE_METHOD);
  const [pin, setPin] = useState("");

  const signer = useMemo(
    () =>
      companyRegistrationSigner(jurisdiction, (companyId) => {
        // Recorded the moment the row exists: a signature that fails after this
        // must not make the review step create a second company.
        adoptCompany(companyId, false);
      }),
    [jurisdiction, adoptCompany],
  );

  const { state, certs, error, start, pick, reset } = useEimzoSign<EimzoRegistration>({
    signer,
    onConfirmed: (registration) => {
      adoptCompany(registration.company_id, true);
      onSigned(registration);
    },
  });

  const busy =
    state === "probing" || state === "listing" || state === "signing" || state === "verifying";

  const methodItems: TabItem[] = EIMZO_METHODS.map((id) => ({
    id,
    label: t(`wizard.eimzo.methods.${id}`),
    testId: `eimzo-method-${id}`,
  }));

  const supported = method === EIMZO_AVAILABLE_METHOD;

  async function handleSign(): Promise<void> {
    reset();
    await start();
  }

  return (
    <section className="space-y-4" data-testid="wizard-eimzo-panel">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.eimzo.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.eimzo.subtitle")}</p>
      </div>

      <Tabs
        variant="segmented"
        items={methodItems}
        value={method}
        onChange={(id) => setMethod(id as EimzoMethod)}
        label={t("wizard.eimzo.title")}
        data-testid="eimzo-methods"
      />

      <UsbTokenArt className="mx-auto my-2" />

      <Card>
        <CardBody className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-brand">
              <UsbIcon size={16} />
            </span>
            <h3 className="text-sm font-semibold text-text">{t("wizard.eimzo.instructionTitle")}</h3>
          </div>
          <ol className="space-y-2.5">
            {INSTRUCTION_STEPS.map((step) => (
              <li key={step} className="flex items-center gap-3">
                <IconTile size="sm" className="h-6 w-6 rounded-full text-xs font-semibold">
                  <span className="num">{step}</span>
                </IconTile>
                <span className="text-sm text-text-muted">
                  {t(`wizard.eimzo.instruction.step${step}`)}
                </span>
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>

      <FormField label={t("wizard.eimzo.pinLabel")} required>
        {({ id }) => (
          <PasswordInput
            id={id}
            inputMode="numeric"
            autoComplete="off"
            value={pin}
            revealLabel={t("wizard.eimzo.revealPin")}
            onChange={(e) => setPin(e.target.value)}
          />
        )}
      </FormField>

      {!supported ? (
        <Alert tone="info" data-testid="eimzo-method-unavailable">
          {t("wizard.eimzo.methodUnavailable")}
        </Alert>
      ) : null}

      {state === "module_missing" ? (
        <Alert tone="warning" title={t("eimzo.moduleMissing.title")} data-testid="eimzo-module-missing">
          {t("eimzo.moduleMissing.body")}
        </Alert>
      ) : null}

      {state === "no_certs" ? (
        <Alert tone="warning" data-testid="eimzo-no-certs">
          {t("eimzo.noCerts")}
        </Alert>
      ) : null}

      {state === "error" ? (
        <Alert tone="danger" title={t("eimzo.errors.title")} data-testid="eimzo-error">
          {t(`eimzo.errors.${error ?? "unknown"}`)}
        </Alert>
      ) : null}

      {state === "success" ? (
        <Alert tone="success" title={t("eimzo.success.title")} data-testid="eimzo-success">
          {t("wizard.eimzo.signedBody")}
        </Alert>
      ) : null}

      {/* More than one certificate on the key: the holder chooses which company
          they are registering, so this cannot be resolved for them. */}
      {state === "selecting" ? (
        <ul className="space-y-2" data-testid="eimzo-select">
          {certs.map((cert) => (
            <li key={cert.id}>
              <button
                type="button"
                onClick={() => void pick(cert.id)}
                className="w-full rounded-md border border-border bg-surface-inset px-3 py-2 text-start text-sm transition-colors hover:border-brand-line"
                data-testid="eimzo-cert-option"
              >
                <span className="block font-medium text-text">{cert.subjectName}</span>
                {cert.tin ? <span className="num block text-xs text-text-muted">{cert.tin}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <Button
        fullWidth
        size="lg"
        disabled={!supported || state === "success" || pin.trim().length === 0}
        loading={busy}
        onClick={() => void handleSign()}
        data-testid="wizard-eimzo"
      >
        {busy ? t(`eimzo.progress.${state}`) : t("wizard.eimzo.sign")}
      </Button>

      <p className="flex items-start gap-2 text-xs text-text-muted">
        <span className="mt-0.5 shrink-0 text-brand">
          <ShieldIcon size={16} />
        </span>
        {t("wizard.eimzo.legalNote")}
      </p>
    </section>
  );
}
