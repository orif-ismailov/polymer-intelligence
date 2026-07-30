import { useState } from "react";

import { useTranslation } from "react-i18next";

import { useAddBankAccount, useRemoveBankAccount } from "@/entities/company";
import type { CompanyDetail } from "@/entities/company";
import { BANK_MFO_LENGTH, CURRENCIES } from "@/shared/config";
import { useEnumLabels } from "@/shared/i18n";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  FormField,
  Input,
  Select,
} from "@/shared/ui";

interface BankSectionProps {
  company: CompanyDetail;
  editable: boolean;
}

const DIGITS = /^\d+$/;

export function BankSection({ company, editable }: BankSectionProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const add = useAddBankAccount(company.id);
  const remove = useRemoveBankAccount(company.id);
  const [adding, setAdding] = useState(false);
  const [removeId, setRemoveId] = useState<number | null>(null);
  const [touched, setTouched] = useState(false);
  const [form, setForm] = useState({ bank_mfo: "", account_number: "", bank_name: "", currency: "UZS" });

  const mfoOk = form.bank_mfo.length === BANK_MFO_LENGTH && DIGITS.test(form.bank_mfo);
  const accountOk = form.account_number.trim().length > 0;
  const valid = mfoOk && accountOk;

  function submit(): void {
    setTouched(true);
    if (!valid) return;
    add.mutate(
      {
        bank_mfo: form.bank_mfo.trim(),
        account_number: form.account_number.trim(),
        bank_name: form.bank_name.trim() || undefined,
        currency: form.currency,
      },
      {
        onSuccess: () => {
          setAdding(false);
          setTouched(false);
          setForm({ bank_mfo: "", account_number: "", bank_name: "", currency: "UZS" });
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader
        action={
          editable && !adding ? (
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              {t("company.addBankAccount")}
            </Button>
          ) : undefined
        }
      >
        <CardTitle>{t("company.bankAccounts")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {company.bank_accounts.length > 0 ? (
          <ul className="divide-y divide-border">
            {company.bank_accounts.map((account) => (
              <li key={account.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="num text-sm font-medium text-text">{account.account_masked}</p>
                  <p className="text-xs text-text-muted">
                    {t("company.bankMfo")} {account.bank_mfo}
                    {account.bank_name ? ` · ${account.bank_name}` : ""} · {account.currency}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {/* Was `{account.status}` — the raw enum, so a Russian card
                      carried an English "unverified" badge. */}
                  <Badge tone={account.status === "verified" ? "success" : "neutral"}>
                    {label("bankAccountStatus", account.status)}
                  </Badge>
                  {editable ? (
                    <button
                      type="button"
                      onClick={() => setRemoveId(account.id)}
                      className="text-xs font-medium text-danger hover:underline"
                    >
                      {t("common.remove")}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">{t("company.noBankAccounts")}</p>
        )}

        {adding ? (
          <div className="space-y-4 rounded-md border border-border bg-surface-2 p-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label={t("company.bankMfo")} error={touched && !mfoOk ? t("wizard.bank.mfoInvalid") : null}>
                {({ id, invalid }) => (
                  <Input
                    id={id}
                    invalid={invalid}
                    inputMode="numeric"
                    maxLength={5}
                    value={form.bank_mfo}
                    onChange={(e) => setForm({ ...form, bank_mfo: e.target.value.replace(/\D+/g, "").slice(0, 5) })}
                  />
                )}
              </FormField>
              <FormField label={t("company.currency")}>
                {({ id }) => (
                  <Select
                    id={id}
                    options={CURRENCIES.map((c) => ({ value: c, label: c }))}
                    value={form.currency}
                    onChange={(e) => setForm({ ...form, currency: e.target.value })}
                  />
                )}
              </FormField>
            </div>
            <FormField label={t("company.accountNumber")} error={touched && !accountOk ? t("wizard.bank.accountInvalid") : null}>
              {({ id, invalid }) => (
                <Input
                  id={id}
                  invalid={invalid}
                  inputMode="numeric"
                  value={form.account_number}
                  onChange={(e) => setForm({ ...form, account_number: e.target.value.replace(/\s+/g, "") })}
                />
              )}
            </FormField>
            <FormField label={t("company.bankName")}>
              {({ id }) => (
                <Input id={id} value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
              )}
            </FormField>
            {add.isError ? <Alert tone="danger" title={t("errors.generic")}>{add.error.message}</Alert> : null}
            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setAdding(false)} disabled={add.isPending}>
                {t("common.cancel")}
              </Button>
              <Button onClick={submit} loading={add.isPending} disabled={!valid}>
                {t("common.add")}
              </Button>
            </div>
          </div>
        ) : null}
      </CardBody>

      <ConfirmDialog
        open={removeId !== null}
        title={t("company.removeBankAccount")}
        description={t("company.removeBankAccountConfirm")}
        confirmLabel={t("common.remove")}
        cancelLabel={t("common.cancel")}
        danger
        loading={remove.isPending}
        onClose={() => setRemoveId(null)}
        onConfirm={() => {
          if (removeId !== null) remove.mutate(removeId, { onSuccess: () => setRemoveId(null) });
        }}
      />
    </Card>
  );
}
