import { type FormEvent, useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import { ApiError } from "@/shared/api";
import { OTP_CODE_LENGTH, OTP_RESEND_FALLBACK_SECONDS } from "@/shared/config";
import { formatPhoneMask } from "@/shared/lib";
import { Alert, Button, FormField, Input } from "@/shared/ui";

import { useCountdown } from "../model/useCountdown";
import { useRequestOtp, useVerifyOtp } from "../model/useOtp";

interface OtpFormProps {
  phone: string;
  initialCooldown: number;
  onVerified: () => void;
  onChangePhone: () => void;
}

export function OtpForm({ phone, initialCooldown, onVerified, onChangePhone }: OtpFormProps) {
  const { t } = useTranslation();
  const [code, setCode] = useState("");
  const verify = useVerifyOtp();
  const requestOtp = useRequestOtp();
  const { remaining, active, start } = useCountdown();

  useEffect(() => {
    start(initialCooldown);
  }, [initialCooldown, start]);

  const codeValid = code.length === OTP_CODE_LENGTH;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (!codeValid) return;
    verify.mutate({ phone, code }, { onSuccess: onVerified });
  }

  function handleResend(): void {
    requestOtp.mutate(phone, {
      onSuccess: () => start(OTP_RESEND_FALLBACK_SECONDS),
      onError: (err) => {
        // Honor the server's Retry-After so the countdown matches reality.
        if (err instanceof ApiError && err.retryAfterSeconds != null) {
          start(err.retryAfterSeconds);
        }
      },
    });
  }

  const verifyError = verify.error;
  const wrongCode = verifyError instanceof ApiError && verifyError.status === 400;

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <p className="text-sm text-text-muted">
        {t("auth.codeSubtitle", { phone: formatPhoneMask(phone) })}{" "}
        <button
          type="button"
          onClick={onChangePhone}
          className="font-medium text-brand underline-offset-2 hover:underline"
        >
          {t("auth.changePhone")}
        </button>
      </p>

      <FormField
        label={t("auth.codeLabel")}
        required
        error={verifyError ? (wrongCode ? t("auth.wrongCode") : verifyError.message) : null}
      >
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={OTP_CODE_LENGTH}
            placeholder="••••••"
            className="text-center text-lg tracking-[0.5em]"
            value={code}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setCode(e.target.value.replace(/\D+/g, "").slice(0, OTP_CODE_LENGTH))}
          />
        )}
      </FormField>

      <Button type="submit" fullWidth size="lg" loading={verify.isPending} disabled={!codeValid}>
        {verify.isPending ? t("auth.verifying") : t("auth.verify")}
      </Button>

      <div className="text-center text-sm">
        {active ? (
          <span className="text-text-muted">{t("auth.resendIn", { seconds: remaining })}</span>
        ) : (
          <button
            type="button"
            onClick={handleResend}
            disabled={requestOtp.isPending}
            className="font-medium text-brand underline-offset-2 hover:underline disabled:opacity-60"
          >
            {t("auth.resend")}
          </button>
        )}
      </div>

      {requestOtp.error instanceof ApiError && requestOtp.error.status === 429 ? (
        <Alert tone="warning" title={t("auth.tooManyRequests")} />
      ) : null}
    </form>
  );
}
