import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Dialog, FormField, PasswordInput } from "@/shared/ui";

import { useStepUpStore } from "../model/stepUpStore";

/**
 * The password re-entry a sensitive action asks for (IMEX-1).
 *
 * Mounted once, near the router root, because the request that triggers it may
 * come from any screen — a dialog owned by the bank form could not serve a
 * mutation fired from anywhere else, and duplicating it per call site is exactly
 * what the bridge exists to avoid.
 */
export function StepUpDialog() {
  const { t } = useTranslation();
  const open = useStepUpStore((s) => s.open);
  const pending = useStepUpStore((s) => s.pending);
  const error = useStepUpStore((s) => s.error);
  const submit = useStepUpStore((s) => s.submit);
  const cancel = useStepUpStore((s) => s.cancel);
  const [password, setPassword] = useState("");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password || pending) return;
    // Clear only on success. Wiping a refused password also disables the confirm
    // button, so a single typo used to mean retyping the whole thing.
    if (await submit(password)) setPassword("");
  };

  const onClose = () => {
    setPassword("");
    cancel();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("stepUp.title")}
      description={t("stepUp.description")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="step-up-form" loading={pending} disabled={!password}>
            {t("stepUp.confirm")}
          </Button>
        </>
      }
    >
      <form id="step-up-form" onSubmit={onSubmit} className="space-y-4">
        {/* The server's refusal belongs on the field, not in a banner above it:
            there is exactly one input here and exactly one thing that can be
            wrong with it. */}
        <FormField
          label={t("stepUp.passwordLabel")}
          error={error ? t(`stepUp.errors.${error}`) : null}
        >
          {({ id, invalid, describedBy }) => (
            <PasswordInput
              id={id}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              autoFocus
            />
          )}
        </FormField>
      </form>
    </Dialog>
  );
}
