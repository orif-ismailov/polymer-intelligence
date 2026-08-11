import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { ApiError } from "@/shared/api";
import { OTP_RESEND_FALLBACK_SECONDS } from "@/shared/config";
import { formatPhoneMask, isValidPhone, normalizePhone } from "@/shared/lib";
import { Alert, Button, FormField, Input } from "@/shared/ui";

import { useRequestOtp } from "../model/useOtp";

interface PhoneFormProps {
  /** Called with the normalized phone + resend cooldown once the OTP is sent. */
  onSent: (phone: string, cooldownSeconds: number) => void;
  initialPhone?: string;
}

export function PhoneForm({ onSent, initialPhone = "" }: PhoneFormProps) {
  const { t } = useTranslation();
  const [display, setDisplay] = useState(() => formatPhoneMask(initialPhone));
  const [touched, setTouched] = useState(false);
  const requestOtp = useRequestOtp();

  const normalized = normalizePhone(display);
  const valid = isValidPhone(display);
  const showError = touched && !valid;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setTouched(true);
    if (!valid) return;
    requestOtp.mutate(normalized, {
      onSuccess: () => onSent(normalized, OTP_RESEND_FALLBACK_SECONDS),
    });
  }

  const error = requestOtp.error;
  const rateLimited = error instanceof ApiError && error.status === 429;

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <FormField
        label={t("auth.phoneLabel")}
        required
        hint={t("auth.phoneHint")}
        error={showError ? t("auth.phoneInvalid") : null}
      >
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            autoFocus
            placeholder={t("auth.phonePlaceholder")}
            value={display}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setDisplay(formatPhoneMask(e.target.value))}
            onBlur={() => setTouched(true)}
          />
        )}
      </FormField>

      {error && !showError ? (
        <Alert tone="danger" title={rateLimited ? t("auth.tooManyRequests") : t("errors.generic")}>
          {rateLimited ? null : error.message}
        </Alert>
      ) : null}

      <Button
        type="submit"
        fullWidth
        size="lg"
        loading={requestOtp.isPending}
        disabled={!valid || requestOtp.isPending}
      >
        {requestOtp.isPending ? t("auth.requestingCode") : t("auth.requestCode")}
      </Button>
    </form>
  );
}
