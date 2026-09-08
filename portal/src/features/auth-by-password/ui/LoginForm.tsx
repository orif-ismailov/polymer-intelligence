import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { ApiError } from "@/shared/api";
import { Alert, Button, FormField, Input, PasswordInput } from "@/shared/ui";

import { useLogin } from "../model/useLogin";

/**
 * Sign-in form: the login and password staff issued.
 *
 * Every failure the server can give — unknown login, wrong password, blocked account,
 * an application nobody has granted yet — comes back as the same 401, and this form
 * shows one sentence for all of them. That is not laziness: telling a visitor "no such
 * login" would let anyone enumerate our customers.
 */
export function LoginForm() {
  const { t } = useTranslation();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useLogin();

  const filled = login.trim().length > 0 && password.length > 0;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (!filled) return;
    signIn.mutate({ login: login.trim(), password });
  }

  const error = signIn.error;
  const rateLimited = error instanceof ApiError && error.status === 429;

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <FormField label={t("auth.loginLabel")} required hint={t("auth.loginHint")}>
        {({ id, invalid, describedBy }) => (
          <Input
            id={id}
            type="text"
            autoComplete="username"
            autoFocus
            spellCheck={false}
            placeholder={t("auth.loginPlaceholder")}
            value={login}
            invalid={invalid}
            aria-describedby={describedBy}
            onChange={(e) => setLogin(e.target.value)}
          />
        )}
      </FormField>

      <FormField label={t("auth.passwordLabel")} required>
        {({ id, invalid, describedBy }) => (
          <PasswordInput
            id={id}
            autoComplete="current-password"
            value={password}
            invalid={invalid}
            aria-describedby={describedBy}
            revealLabel={t("auth.revealPassword")}
            onChange={(e) => setPassword(e.target.value)}
          />
        )}
      </FormField>

      {error ? (
        <Alert
          tone="danger"
          title={rateLimited ? t("auth.tooManyRequests") : t("auth.invalidCredentials")}
        >
          {rateLimited ? t("auth.tryLater") : null}
        </Alert>
      ) : null}

      <Button
        type="submit"
        fullWidth
        size="lg"
        loading={signIn.isPending}
        disabled={!filled || signIn.isPending}
      >
        {signIn.isPending ? t("auth.signingIn") : t("auth.signIn")}
      </Button>
    </form>
  );
}
