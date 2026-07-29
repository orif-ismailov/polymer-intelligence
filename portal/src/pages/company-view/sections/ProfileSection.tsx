import { useState } from "react";

import { useTranslation } from "react-i18next";

import { useUpdateCompanyProfile } from "@/entities/company";
import type { CompanyDetail } from "@/entities/company";
import { useEnumLabels } from "@/shared/i18n";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  SpecItem,
  SpecList,
  CardTitle,
  FormField,
  Input,
} from "@/shared/ui";

interface ProfileSectionProps {
  company: CompanyDetail;
  editable: boolean;
}

interface Row {
  label: string;
  value: string | null;
}

export function ProfileSection({ company, editable }: ProfileSectionProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const [editing, setEditing] = useState(false);
  const update = useUpdateCompanyProfile(company.id);

  const [form, setForm] = useState({
    legal_name: company.legal_name ?? "",
    short_name: company.short_name ?? "",
    legal_form: company.legal_form ?? "",
    legal_address: company.legal_address ?? "",
    director_name: company.director_name ?? "",
  });

  function save(): void {
    update.mutate(
      {
        legal_name: form.legal_name.trim() || undefined,
        short_name: form.short_name.trim() || undefined,
        legal_form: form.legal_form.trim() || undefined,
        legal_address: form.legal_address.trim() || undefined,
        director_name: form.director_name.trim() || undefined,
      },
      { onSuccess: () => setEditing(false) },
    );
  }

  const rows: Row[] = [
    { label: t("companies.jurisdiction"), value: label("jurisdiction", company.jurisdiction) },
    { label: t("companies.taxId"), value: company.tax_id },
    { label: t("companies.legalName"), value: company.legal_name },
    { label: t("companies.shortName"), value: company.short_name },
    { label: t("company.legalForm"), value: company.legal_form },
    { label: t("company.director"), value: company.director_name },
    { label: t("company.legalAddress"), value: company.legal_address },
    { label: t("company.publicId"), value: company.public_id },
  ];

  return (
    <Card>
      <CardHeader
        action={
          editable && !editing ? (
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              {t("company.editProfile")}
            </Button>
          ) : undefined
        }
      >
        <CardTitle>{t("company.profile")}</CardTitle>
      </CardHeader>
      <CardBody>
        {editing ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label={t("companies.legalName")}>
                {({ id }) => (
                  <Input id={id} value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} />
                )}
              </FormField>
              <FormField label={t("companies.shortName")}>
                {({ id }) => (
                  <Input id={id} value={form.short_name} onChange={(e) => setForm({ ...form, short_name: e.target.value })} />
                )}
              </FormField>
              <FormField label={t("company.legalForm")}>
                {({ id }) => (
                  <Input id={id} value={form.legal_form} onChange={(e) => setForm({ ...form, legal_form: e.target.value })} />
                )}
              </FormField>
              <FormField label={t("company.director")}>
                {({ id }) => (
                  <Input id={id} value={form.director_name} onChange={(e) => setForm({ ...form, director_name: e.target.value })} />
                )}
              </FormField>
            </div>
            <FormField label={t("company.legalAddress")}>
              {({ id }) => (
                <Input id={id} value={form.legal_address} onChange={(e) => setForm({ ...form, legal_address: e.target.value })} />
              )}
            </FormField>
            {update.isError ? <Alert tone="danger" title={t("errors.generic")}>{update.error.message}</Alert> : null}
            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setEditing(false)} disabled={update.isPending}>
                {t("common.cancel")}
              </Button>
              <Button onClick={save} loading={update.isPending}>
                {t("common.save")}
              </Button>
            </div>
          </div>
        ) : (
          <SpecList>
            {rows.map((row) => (
              <SpecItem
                key={row.label}
                label={row.label}
                value={row.value ?? t("common.notSpecified")}
              />
            ))}
          </SpecList>
        )}
      </CardBody>
    </Card>
  );
}
