import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { ApiError } from "@/shared/api";
import { MIN_PASSWORD_LENGTH } from "@/shared/config";
import { Alert, Button, FormField, PasswordInput } from "@/shared/ui";

import { useChangePassword } from "../model/useChangePassword";

interface ChangePasswordFormProps {
  /** Called after the new password is accepted and the session is refreshed. */
  onChanged: () => void;
}

/**
 * Set a new password.
 *
 * The current one is required, so a screen left open cannot be turned into someone
 * else's account. The confirmation field is checked here rather than on the server —
 * a typo is not a security event, and a round trip to say so is just slower.
 */
export function ChangePasswordForm({ onChanged }: ChangePasswordFormProps) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState(false);
  const change = useChangePassword();

  const tooShort = next.length > 0 && next.length < MIN_PASSWORD_LENGTH;
  const mismatch = confirm.length > 0 && confirm !== next;
  const filled = current.length > 0 && next.length >= MIN_PASSWORD_LENGTH && confirm === next;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setTouched(true);
    if (!filled) return;
    change.mutate({ current_password: current, new_password: next }, { onSuccess: onChanged });
  }

  const error = change.error;
  const wrongCurrent = error instanceof ApiError && error.status === 400;
  const rateLimited = error instanceof ApiError && error.status === 429;

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <FormField
        label={t("password.current")}
        required
        hint={t("password.currentHint")}
        error={wrongCurrent ? t("password.wrongCurrent") : null}
      >
        {({ id, invalid, describedBy }) => (
          <PasswordInput
            id={id}
            autoComplete="current-password"
            autoFocus
            value={current}
            invalid={invalid}
            aria-describedby={describedBy}
            revealLabel={t("auth.revealPassword")}
            onChange={(e) => setCurrent(e.target.value)}
          />
        )}
      </FormField>

      <FormField
        label={t("password.new")}
        required
        hint={t("password.newHint", { n: MIN_PASSWORD_LENGTH })}
        error={touched && tooShort ? t("password.tooShort", { n: MIN_PASSWORD_LENGTH }) : null}
      >
        {({ id, invalid, describedBy }) => (
          <PasswordInput
            id={id}
            autoComplete="new-password"
            value={next}
            invalid={invalid}
            aria-describedby={describedBy}
            revealLabel={t("auth.revealPassword")}
            onChange={(e) => setNext(e.target.value)}
            onBlur={() => setTouched(true)}
          />
        )}
      </FormField>

      <FormField
        label={t("password.confirm")}
        required
        error={mismatch ? t("password.mismatch") : null}
      >
        {({ id, invalid, describedBy }) => (
          <PasswordInput
            id={id}
            autoComplete="new-password"
            value={confirm}
            invalid={invalid}
            aria-describedby={describedBy}
            revealLabel={t("auth.revealPassword")}
            onChange={(e) => setConfirm(e.target.value)}
          />
        )}
      </FormField>

      {error && !wrongCurrent ? (
        <Alert
          tone="danger"
          title={rateLimited ? t("auth.tooManyRequests") : t("errors.generic")}
        >
          {rateLimited ? t("auth.tryLater") : null}
        </Alert>
      ) : null}

      <Button
        type="submit"
        fullWidth
        size="lg"
        loading={change.isPending}
        disabled={!filled || change.isPending}
      >
        {change.isPending ? t("password.saving") : t("password.submit")}
      </Button>
    </form>
  );
}
