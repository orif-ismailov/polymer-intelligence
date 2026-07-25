import { useEffect } from "react";

import { useTranslation } from "react-i18next";

import { Alert, Button, Dialog, Spinner } from "@/shared/ui";

import { useEimzoSign } from "../model/useEimzoSign";
import type { EimzoVerifyOut } from "../model/api";

interface EimzoSignDialogProps {
  open: boolean;
  companyId: number | null;
  onClose: () => void;
  onConfirmed?: (result: EimzoVerifyOut) => void;
}

const DOWNLOAD_LINKS = [
  { href: "https://e-imzo.uz", key: "eimzo" },
  { href: "https://my.soliq.uz", key: "soliq" },
] as const;

/**
 * Controlled E-IMZO signing dialog (TA2.1). Auto-starts the probe→list→sign→verify
 * flow when opened with a companyId; renders every state incl. module-missing
 * (with install links) and typed error mapping. Reused by the wizard and the
 * verification-status screen.
 */
export function EimzoSignDialog({ open, companyId, onClose, onConfirmed }: EimzoSignDialogProps) {
  const { t } = useTranslation();
  const { state, certs, error, result, start, pick, reset } = useEimzoSign({ onConfirmed });

  useEffect(() => {
    if (open && companyId != null && state === "idle") {
      void start(companyId);
    }
  }, [open, companyId, state, start]);

  function handleClose(): void {
    reset();
    onClose();
  }

  function handleRetry(): void {
    if (companyId != null) {
      reset();
      void start(companyId);
    }
  }

  const busy = state === "probing" || state === "listing" || state === "signing" || state === "verifying";

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={t("eimzo.title")}
      description={t("eimzo.subtitle")}
    >
      <div className="space-y-4" data-testid="eimzo-dialog">
        {busy ? (
          <div className="flex items-center gap-3" data-testid={`eimzo-state-${state}`}>
            <Spinner />
            <p className="text-sm text-text-muted">{t(`eimzo.progress.${state}`)}</p>
          </div>
        ) : null}

        {state === "module_missing" ? (
          <div className="space-y-3" data-testid="eimzo-module-missing">
            <Alert tone="warning" title={t("eimzo.moduleMissing.title")}>
              {t("eimzo.moduleMissing.body")}
            </Alert>
            <ul className="space-y-1 text-sm">
              {DOWNLOAD_LINKS.map((link) => (
                <li key={link.key}>
                  <a
                    className="text-primary underline"
                    href={link.href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t(`eimzo.moduleMissing.link_${link.key}`)}
                  </a>
                </li>
              ))}
            </ul>
            <p className="text-xs text-text-muted">{t("eimzo.moduleMissing.desktopHint")}</p>
            <Button variant="secondary" onClick={handleRetry} data-testid="eimzo-retry">
              {t("eimzo.retry")}
            </Button>
          </div>
        ) : null}

        {state === "no_certs" ? (
          <div className="space-y-3" data-testid="eimzo-no-certs">
            <Alert tone="warning">{t("eimzo.noCerts")}</Alert>
            <Button variant="secondary" onClick={handleRetry} data-testid="eimzo-retry">
              {t("eimzo.retry")}
            </Button>
          </div>
        ) : null}

        {state === "selecting" ? (
          <div className="space-y-2" data-testid="eimzo-select">
            <p className="text-sm text-text-muted">{t("eimzo.selectCert")}</p>
            <ul className="space-y-2">
              {certs.map((cert) => (
                <li key={cert.id}>
                  <button
                    type="button"
                    onClick={() => void pick(cert.id)}
                    className="w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:border-primary"
                    data-testid="eimzo-cert-option"
                  >
                    <span className="block font-medium text-text">{cert.subjectName}</span>
                    {cert.tin ? (
                      <span className="block text-xs text-text-muted">{cert.tin}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {state === "success" ? (
          <Alert tone="success" title={t("eimzo.success.title")}>
            <span data-testid="eimzo-success">
              {t("eimzo.success.body", { holder: result?.holder_masked ?? "" })}
            </span>
          </Alert>
        ) : null}

        {state === "error" ? (
          <div className="space-y-3" data-testid="eimzo-error">
            <Alert tone="danger" title={t("eimzo.errors.title")}>
              {t(`eimzo.errors.${error ?? "unknown"}`)}
            </Alert>
            <Button variant="secondary" onClick={handleRetry} data-testid="eimzo-retry">
              {t("eimzo.retry")}
            </Button>
          </div>
        ) : null}
      </div>

      <div className="mt-5 flex justify-end">
        <Button variant={state === "success" ? "primary" : "ghost"} onClick={handleClose}>
          {state === "success" ? t("eimzo.done") : t("common.cancel")}
        </Button>
      </div>
    </Dialog>
  );
}
