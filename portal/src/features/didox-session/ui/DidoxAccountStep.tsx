import { useState, type FormEvent } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { didoxStatusKey } from "@/entities/edi";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  PasswordInput,
} from "@/shared/ui";

import { useDidoxSession } from "../model/useDidoxSession";

interface DidoxAccountStepProps {
  companyId: number;
  taxId: string;
  /** The account's phone, offered as the Didox contact number. */
  phone: string;
}

/**
 * Step 1 — the company gets a Didox account, or proves it already has one.
 *
 * Signing in comes first: a company that registered on didox.uz needs only its
 * key, and a successful sign-in is itself the proof (it also reads whether the
 * offer is already signed, so such a company may skip step 2 entirely).
 *
 * The email and password are the owner's login at didox.uz — typed here, sent
 * to Didox, never stored by us. Didox's validator refuses `+` in the email.
 */
export function DidoxAccountStep({
  companyId,
  taxId,
  phone,
}: DidoxAccountStepProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const session = useDidoxSession(companyId, taxId);
  const [email, setEmail] = useState("");
  const [mobile, setMobile] = useState(phone.replace(/\D/g, ""));
  const [password, setPassword] = useState("");

  const emailError =
    email && (!email.includes("@") || email.includes("+"))
      ? t("didoxOnboarding.account.emailInvalid")
      : null;
  const mobileError =
    mobile && !/^\d{9,15}$/.test(mobile)
      ? t("didoxOnboarding.account.mobileInvalid")
      : null;
  const passwordError =
    password && password.length < 8
      ? t("didoxOnboarding.account.passwordShort")
      : null;
  const canRegister =
    email !== "" &&
    mobile !== "" &&
    password !== "" &&
    !emailError &&
    !mobileError &&
    !passwordError;

  async function refresh(): Promise<void> {
    await queryClient.invalidateQueries({
      queryKey: didoxStatusKey(companyId),
    });
  }

  async function signIn(): Promise<void> {
    if (await session.open()) await refresh();
  }

  async function register(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!canRegister) return;
    if (await session.signup({ email: email.trim(), mobile, password }))
      await refresh();
  }

  return (
    <div className="space-y-4" data-testid="didox-account-step">
      <Card>
        <CardHeader>
          <CardTitle>{t("didoxOnboarding.account.haveTitle")}</CardTitle>
          <CardDescription>
            {t("didoxOnboarding.account.haveBody")}
          </CardDescription>
        </CardHeader>
        <CardBody>
          <Button
            type="button"
            variant="secondary"
            disabled={session.minting}
            onClick={() => void signIn()}
            data-testid="didox-sign-in"
          >
            {session.minting
              ? t("didox.connecting")
              : t("didoxOnboarding.account.signIn")}
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("didoxOnboarding.account.registerTitle")}</CardTitle>
          <CardDescription>
            {t("didoxOnboarding.account.registerBody")}
          </CardDescription>
        </CardHeader>
        <CardBody>
          <form
            className="space-y-4"
            onSubmit={(e) => void register(e)}
            data-testid="didox-register-form"
          >
            <FormField
              label={t("didoxOnboarding.account.email")}
              required
              error={emailError}
            >
              {({ id, invalid }) => (
                <Input
                  id={id}
                  type="email"
                  autoComplete="email"
                  value={email}
                  aria-invalid={invalid}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
            </FormField>
            <FormField
              label={t("didoxOnboarding.account.mobile")}
              required
              error={mobileError}
              hint={t("didoxOnboarding.account.mobileHint")}
            >
              {({ id, invalid }) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  autoComplete="tel"
                  value={mobile}
                  aria-invalid={invalid}
                  onChange={(e) => setMobile(e.target.value.replace(/\D/g, ""))}
                />
              )}
            </FormField>
            <FormField
              label={t("didoxOnboarding.account.password")}
              required
              error={passwordError}
              hint={t("didoxOnboarding.account.passwordHint")}
            >
              {({ id, invalid }) => (
                <PasswordInput
                  id={id}
                  autoComplete="new-password"
                  revealLabel={t("auth.revealPassword")}
                  value={password}
                  aria-invalid={invalid}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </FormField>
            <Button
              type="submit"
              disabled={!canRegister || session.minting}
              data-testid="didox-register"
            >
              {session.minting
                ? t("didox.connecting")
                : t("didoxOnboarding.account.register")}
            </Button>
          </form>
        </CardBody>
      </Card>

      {session.error && (
        <Alert tone="danger">
          {t(`didox.errors.${session.error}`, {
            message: session.errorMessage ?? "",
          })}
        </Alert>
      )}
    </div>
  );
}
