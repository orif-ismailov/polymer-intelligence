import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore, useLogout, useUpdateAccount } from "@/entities/account";
import { SUPPORTED_LANGS, coerceLang } from "@/shared/i18n";
import { THEME_MODES, formatPhoneMask, useThemeStore, type ThemeMode } from "@/shared/lib";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  FormField,
  Input,
  PageHeader,
  Select,
} from "@/shared/ui";

export function SettingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const account = useAuthStore((s) => s.account);
  const update = useUpdateAccount();
  const logout = useLogout();

  const themeMode = useThemeStore((s) => s.mode);
  const setThemeMode = useThemeStore((s) => s.setMode);

  const [name, setName] = useState(account?.name ?? "");
  const [language, setLanguage] = useState(coerceLang(account?.language));
  const [saved, setSaved] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);

  const dirty = name !== (account?.name ?? "") || language !== coerceLang(account?.language);

  function save(): void {
    setSaved(false);
    update.mutate(
      { name: name.trim(), language },
      { onSuccess: () => setSaved(true) },
    );
  }

  function handleLogout(): void {
    logout.mutate(undefined, {
      onSettled: () => {
        void navigate("/cabinet/login", { replace: true });
      },
    });
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader title={t("settings.title")} />

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.profile")}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <FormField label={t("settings.phone")}>
            {({ id }) => (
              <Input id={id} value={account ? formatPhoneMask(account.phone) : ""} disabled readOnly />
            )}
          </FormField>

          <FormField label={t("settings.name")}>
            {({ id }) => (
              <Input
                id={id}
                value={name}
                placeholder={t("settings.namePlaceholder")}
                onChange={(e) => {
                  setName(e.target.value);
                  setSaved(false);
                }}
              />
            )}
          </FormField>

          <FormField label={t("settings.language")}>
            {({ id }) => (
              <Select
                id={id}
                value={language}
                options={SUPPORTED_LANGS.map((lang) => ({ value: lang, label: t(`language.${lang}`) }))}
                onChange={(e) => {
                  setLanguage(coerceLang(e.target.value));
                  setSaved(false);
                }}
              />
            )}
          </FormField>

          {saved ? <Alert tone="success" title={t("settings.saved")} /> : null}
          {update.isError ? <Alert tone="danger" title={t("errors.generic")}>{update.error.message}</Alert> : null}

          <div className="flex justify-end">
            <Button onClick={save} loading={update.isPending} disabled={!dirty}>
              {t("settings.save")}
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.appearance")}</CardTitle>
        </CardHeader>
        <CardBody>
          <FormField label={t("settings.theme")} hint={t("settings.themeHint")}>
            {({ id }) => (
              <Select
                id={id}
                value={themeMode}
                options={THEME_MODES.map((mode) => ({
                  value: mode,
                  label: t(`theme.${mode}`),
                }))}
                onChange={(e) => {
                  setThemeMode(e.target.value as ThemeMode);
                }}
              />
            )}
          </FormField>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="flex items-center justify-between gap-4">
          <div>
            <p className="font-medium text-text">{t("settings.logout")}</p>
          </div>
          <Button variant="danger" onClick={() => setConfirmLogout(true)} loading={logout.isPending}>
            {t("nav.logout")}
          </Button>
        </CardBody>
      </Card>

      <ConfirmDialog
        open={confirmLogout}
        title={t("settings.logout")}
        description={t("settings.logoutConfirm")}
        confirmLabel={t("nav.logout")}
        cancelLabel={t("common.cancel")}
        danger
        loading={logout.isPending}
        onClose={() => setConfirmLogout(false)}
        onConfirm={handleLogout}
      />
    </div>
  );
}
