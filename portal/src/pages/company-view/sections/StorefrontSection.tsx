import { useState } from "react";

import { useTranslation } from "react-i18next";

import {
  useUpdateCompanyPublicProfile,
  useUploadCompanyCover,
} from "@/entities/company";
import type { CompanyDetail } from "@/entities/company";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dropzone,
  FormField,
  Input,
  SpecItem,
  SpecList,
  Textarea,
} from "@/shared/ui";

interface StorefrontSectionProps {
  company: CompanyDetail;
}

/** A whole non-negative number, or `null` for a cleared field. */
function parseCount(raw: string): number | null | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isInteger(n) && n >= 0 ? n : undefined;
}

/**
 * «Витрина» — the copy a carrier's PUBLIC profile prints.
 *
 * Deliberately NOT gated on the `editable` flag every other section on this page
 * takes. That flag tracks whether verification has decided, and this is the one
 * block that must stay editable AFTER it has: a carrier only appears in the
 * public directory once it is `verified`, so gating this the same way would mean
 * the text on its public page could be written only before anyone could see it.
 * The backend agrees — `PATCH /public-profile` skips the editability gate and
 * narrows what it can reach instead.
 *
 * Only rendered for a company that declared the logistics role; there is no
 * storefront block for the other account types yet.
 */
export function StorefrontSection({ company }: StorefrontSectionProps) {
  const { t } = useTranslation();
  const update = useUpdateCompanyPublicProfile(company.id);
  const uploadCover = useUploadCompanyCover(company.id);
  const profile = company.logistics_profile ?? {};

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    description: profile.description ?? "",
    years_experience: profile.years_experience?.toString() ?? "",
    projects_completed: profile.projects_completed?.toString() ?? "",
  });

  const years = parseCount(form.years_experience);
  const projects = parseCount(form.projects_completed);
  const invalid = years === undefined || projects === undefined;

  function save(): void {
    if (invalid) return;
    update.mutate(
      {
        description: form.description.trim() || null,
        years_experience: years,
        projects_completed: projects,
      },
      { onSuccess: () => setEditing(false) },
    );
  }

  return (
    <Card>
      <CardHeader
        action={
          editing ? null : (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {t("common.edit")}
            </Button>
          )
        }
      >
        <CardTitle>{t("company.storefront.title")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="text-xs text-text-muted">{t("company.storefront.hint")}</p>

        {/* The hero behind the logo on the public profile. Its own control
            rather than a form field: a file upload is not something to hold in
            local state until someone presses Save. */}
        <div className="space-y-2">
          {company.cover_url ? (
            <img
              src={company.cover_url}
              alt=""
              className="h-28 w-full rounded-md border border-border object-cover"
            />
          ) : null}
          <Dropzone
            label={t("company.storefront.cover")}
            hint={t("company.storefront.coverHint")}
            accept="image/jpeg,image/png"
            disabled={uploadCover.isPending}
            onFiles={(files) => {
              const file = files[0];
              if (file) uploadCover.mutate(file);
            }}
          />
          {uploadCover.isError ? (
            <Alert tone="danger">{t("company.storefront.coverFailed")}</Alert>
          ) : null}
        </div>

        {editing ? (
          <div className="space-y-4">
            <FormField label={t("company.storefront.description")}>
              {({ id }) => (
                <Textarea
                  id={id}
                  rows={3}
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                />
              )}
            </FormField>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label={t("company.storefront.experience")}
                error={years === undefined ? t("company.storefront.countInvalid") : null}
              >
                {({ id, invalid: bad }) => (
                  <Input
                    id={id}
                    inputMode="numeric"
                    value={form.years_experience}
                    invalid={bad}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, years_experience: e.target.value }))
                    }
                  />
                )}
              </FormField>
              <FormField
                label={t("company.storefront.projects")}
                error={projects === undefined ? t("company.storefront.countInvalid") : null}
              >
                {({ id, invalid: bad }) => (
                  <Input
                    id={id}
                    inputMode="numeric"
                    value={form.projects_completed}
                    invalid={bad}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, projects_completed: e.target.value }))
                    }
                  />
                )}
              </FormField>
            </div>

            {update.isError ? (
              <Alert tone="danger" title={t("errors.generic")}>
                {t("company.storefront.saveFailed")}
              </Alert>
            ) : null}

            <div className="flex gap-2">
              <Button onClick={save} loading={update.isPending} disabled={invalid}>
                {t("common.save")}
              </Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>
                {t("common.cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <SpecList>
            <SpecItem
              label={t("company.storefront.description")}
              value={profile.description?.trim() || "—"}
              span={2}
            />
            <SpecItem
              label={t("company.storefront.experience")}
              value={profile.years_experience?.toString() ?? "—"}
              numeric
            />
            <SpecItem
              label={t("company.storefront.projects")}
              value={profile.projects_completed?.toString() ?? "—"}
              numeric
            />
          </SpecList>
        )}
      </CardBody>
    </Card>
  );
}
