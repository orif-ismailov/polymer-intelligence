import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { useDeleteAccount } from "@/entities/account";
import { ApiError, detailCode } from "@/shared/api";
import { Alert, Button, Card, CardBody, Dialog, FormField, PasswordInput } from "@/shared/ui";

/**
 * «Удалить аккаунт» — the web half of the deletion path both app stores require.
 *
 * The password is asked for in the dialog rather than trusted from the session: a
 * screen left open must not be enough to erase somebody. On success the server
 * has already revoked the session and cleared the cookie, so the page moves to the
 * public `/account-deletion` (which says what was kept) and only THEN forgets the
 * local session — in the other order `RequireAuth` would bounce to the login.
 */
export function DeleteAccountCard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useDeleteAccount();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");

  const error = remove.error;
  const wrongPassword =
    error instanceof ApiError && error.status === 400 && detailCode(error) === "invalid_password";
  const rateLimited = error instanceof ApiError && error.status === 429;
  const fieldError = wrongPassword
    ? t("settings.deleteAccount.wrongPassword")
    : rateLimited
      ? t("settings.deleteAccount.rateLimited")
      : null;
  const otherError = error && !wrongPassword && !rateLimited;

  function close(): void {
    if (remove.isPending) return;
    setOpen(false);
    setPassword("");
    remove.reset();
  }

  function submit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (!password || remove.isPending) return;
    remove.mutate(password, {
      onSuccess: () => {
        void navigate("/account-deletion", { replace: true, state: { deleted: true } });
        remove.forgetSession();
      },
    });
  }

  return (
    <>
      <Card>
        <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="font-medium text-text">{t("settings.deleteAccount.title")}</p>
            <p className="mt-1 text-sm text-text-muted">{t("settings.deleteAccount.description")}</p>
            <Link
              to="/account-deletion"
              className="mt-2 inline-block text-sm font-medium text-brand hover:underline"
            >
              {t("settings.deleteAccount.learnMore")}
            </Link>
          </div>
          <Button variant="danger" onClick={() => setOpen(true)} className="shrink-0">
            {t("settings.deleteAccount.action")}
          </Button>
        </CardBody>
      </Card>

      <Dialog
        open={open}
        onClose={close}
        title={t("settings.deleteAccount.dialogTitle")}
        description={t("settings.deleteAccount.dialogBody")}
        footer={
          <>
            <Button variant="ghost" onClick={close} disabled={remove.isPending}>
              {t("common.cancel")}
            </Button>
            <Button
              type="submit"
              form="delete-account-form"
              variant="danger"
              loading={remove.isPending}
              disabled={!password}
            >
              {t("settings.deleteAccount.confirm")}
            </Button>
          </>
        }
      >
        <form id="delete-account-form" onSubmit={submit} className="space-y-4" noValidate>
          <FormField label={t("settings.deleteAccount.password")} required error={fieldError}>
            {({ id, invalid, describedBy }) => (
              <PasswordInput
                id={id}
                autoComplete="current-password"
                autoFocus
                value={password}
                invalid={invalid}
                aria-describedby={describedBy}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </FormField>
          {otherError ? <Alert tone="danger" title={t("errors.generic")} /> : null}
        </form>
      </Dialog>
    </>
  );
}
