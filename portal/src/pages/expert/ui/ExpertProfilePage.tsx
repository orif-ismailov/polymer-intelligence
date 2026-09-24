import { type ReactNode, useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import {
  TechnologistAvatar,
  useOwnTechnologist,
  useOwnTechnologistPhoto,
  useSaveTechnologist,
  useSubmitTechnologist,
  useTechFacets,
  useUploadTechnologistPhoto,
  type TechnologistOwnProfile,
  type TechnologistProfileInput,
} from "@/entities/technologist";
import { detailError } from "@/shared/api";
import {
  Alert,
  Button,
  Card,
  CardBody,
  ChipInput,
  Dropzone,
  ErrorView,
  FormField,
  Input,
  LinkButton,
  LoadingView,
  PageHeader,
  Textarea,
  ToggleChips,
} from "@/shared/ui";

const FIELDS: (keyof TechnologistProfileInput)[] = [
  "full_name",
  "title",
  "country",
  "city",
  "years_experience",
  "projects_count",
  "countries_count",
  "bio",
  "industries",
  "processes",
  "materials",
  "equipment_brands",
  "work_formats",
  "languages",
  "contact_phone",
  "contact_email",
];

function toInput(profile: TechnologistOwnProfile): TechnologistProfileInput {
  return Object.fromEntries(FIELDS.map((k) => [k, profile[k]])) as unknown as TechnologistProfileInput;
}

/**
 * `/cabinet/expert` — the technologist's professional profile.
 *
 * Saving is a draft; «Отправить на проверку» sends it to staff. A published
 * expert who edits keeps being listed as the APPROVED version until the edit is
 * approved too — the banner says which version the catalog is showing.
 */
export function ExpertProfilePage() {
  const { t } = useTranslation();
  const own = useOwnTechnologist();
  const facets = useTechFacets();
  const save = useSaveTechnologist();
  const submit = useSubmitTechnologist();
  const photo = useUploadTechnologistPhoto();
  const [draft, setDraft] = useState<TechnologistProfileInput | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const photoSrc = useOwnTechnologistPhoto(Boolean(own.data?.photo_url));

  useEffect(() => {
    if (own.data && draft === null) setDraft(toInput(own.data));
  }, [own.data, draft]);

  if (own.isLoading || !draft) return <LoadingView label={t("common.loading")} />;
  if (own.isError || !own.data) return <ErrorView title={t("errors.loadFailed")} />;

  const profile = own.data;
  const f = facets.data;
  const set = <K extends keyof TechnologistProfileInput>(k: K, v: TechnologistProfileInput[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));
  const str = (k: keyof TechnologistProfileInput) => (e: { target: { value: string } }) =>
    set(k, (e.target.value || null) as never);
  const num = (k: keyof TechnologistProfileInput) => (e: { target: { value: string } }) => {
    const digits = e.target.value.replace(/\D/g, "");
    set(k, (digits === "" ? null : Number(digits)) as never);
  };
  // Flagged by the server's refusal, and only while the field is still empty —
  // a fixed field stops shouting before the next submit.
  const isEmpty = (k: keyof TechnologistProfileInput) => {
    const v = draft[k];
    return v === null || v === "" || (Array.isArray(v) && v.length === 0);
  };
  const flag = (k: keyof TechnologistProfileInput) =>
    missing.includes(k) && isEmpty(k) ? t("expert.profile.required") : null;

  async function saveAndSubmit(): Promise<void> {
    if (!draft) return;
    setMissing([]);
    await save.mutateAsync(draft);
    try {
      await submit.mutateAsync();
    } catch (err) {
      if (detailError(err) === "profile_incomplete") {
        const body = (err as { detail?: { detail?: { missing?: string[] } } }).detail;
        setMissing(body?.detail?.missing ?? []);
      }
    }
  }

  const busy = save.isPending || submit.isPending;

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <PageHeader
        title={t("expert.profile.title")}
        subtitle={t("expert.profile.subtitle")}
        actions={
          profile.is_listed ? (
            <LinkButton to={`/technologists/${profile.id}`} variant="outline">
              {t("expert.profile.viewPublic")}
            </LinkButton>
          ) : null
        }
      />

      <div className="mt-5 space-y-5">
        <StatusBanner profile={profile} />

        <Card>
          <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <TechnologistAvatar photoUrl={photoSrc} size="lg" />
            <Dropzone
              className="flex-1"
              label={t("expert.profile.photo")}
              hint={t("expert.profile.photoHint")}
              accept="image/jpeg,image/png"
              disabled={photo.isPending || profile.status === "suspended"}
              onFiles={(files) => {
                const file = files[0];
                if (file) photo.mutate(file);
              }}
            />
          </CardBody>
        </Card>

        <Card>
          <CardBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label={t("expert.profile.fullName")} required error={flag("full_name")}>
                {({ id, invalid }) => (
                  <Input id={id} invalid={invalid} value={draft.full_name ?? ""} onChange={str("full_name")} />
                )}
              </FormField>
              <FormField label={t("expert.profile.titleField")} required error={flag("title")}>
                {({ id, invalid }) => (
                  <Input
                    id={id}
                    invalid={invalid}
                    value={draft.title ?? ""}
                    placeholder={t("expert.profile.titlePlaceholder")}
                    onChange={str("title")}
                  />
                )}
              </FormField>
              <FormField label={t("techRequest.form.country")} required error={flag("country")}>
                {({ id, invalid }) => (
                  <Input
                    id={id}
                    invalid={invalid}
                    maxLength={2}
                    className="num uppercase"
                    value={draft.country ?? ""}
                    onChange={(e) => set("country", e.target.value.toUpperCase() || null)}
                  />
                )}
              </FormField>
              <FormField label={t("techRequest.form.city")}>
                {({ id }) => <Input id={id} value={draft.city ?? ""} onChange={str("city")} />}
              </FormField>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField label={t("technologists.fields.years")} required error={flag("years_experience")}>
                {({ id, invalid }) => (
                  <Input id={id} invalid={invalid} inputMode="numeric" className="num" value={draft.years_experience ?? ""} onChange={num("years_experience")} />
                )}
              </FormField>
              <FormField label={t("technologists.fields.projects")}>
                {({ id }) => (
                  <Input id={id} inputMode="numeric" className="num" value={draft.projects_count ?? ""} onChange={num("projects_count")} />
                )}
              </FormField>
              <FormField label={t("technologists.fields.countries")}>
                {({ id }) => (
                  <Input id={id} inputMode="numeric" className="num" value={draft.countries_count ?? ""} onChange={num("countries_count")} />
                )}
              </FormField>
            </div>
            <FormField label={t("expert.profile.bio")}>
              {({ id }) => (
                <Textarea id={id} rows={4} value={draft.bio ?? ""} placeholder={t("expert.profile.bioPlaceholder")} onChange={str("bio")} />
              )}
            </FormField>
          </CardBody>
        </Card>

        <Card>
          <CardBody className="space-y-5">
            <ChipsField label={t("technologists.fields.processes")} required error={flag("processes")}>
              <ToggleChips
                label={t("technologists.fields.processes")}
                options={f?.processes ?? []}
                value={draft.processes}
                onChange={(v) => set("processes", v)}
                renderLabel={(o) => t(`technologists.process.${o}`)}
              />
            </ChipsField>
            <ChipsField label={t("technologists.fields.materials")}>
              <ToggleChips
                label={t("technologists.fields.materials")}
                options={f?.materials ?? []}
                value={draft.materials}
                onChange={(v) => set("materials", v)}
                renderLabel={(o) => o}
              />
            </ChipsField>
            <ChipsField label={t("technologists.fields.industries")}>
              <ToggleChips
                label={t("technologists.fields.industries")}
                options={f?.industries ?? []}
                value={draft.industries}
                onChange={(v) => set("industries", v)}
                renderLabel={(o) => t(`technologists.industry.${o}`)}
              />
            </ChipsField>
            <FormField label={t("technologists.fields.equipment")} hint={t("expert.profile.equipmentHint")}>
              {({ id }) => (
                <ChipInput
                  id={id}
                  values={draft.equipment_brands}
                  onChange={(v) => set("equipment_brands", v)}
                  placeholder="Reifenhäuser, Engel, Haitian…"
                  addLabel={t("common.add")}
                  removeLabel={t("common.remove")}
                  max={30}
                />
              )}
            </FormField>
            <ChipsField label={t("technologists.fields.formats")} required error={flag("work_formats")}>
              <ToggleChips
                label={t("technologists.fields.formats")}
                options={f?.profile_formats ?? []}
                value={draft.work_formats}
                onChange={(v) => set("work_formats", v)}
                renderLabel={(o) => t(`technologists.format.${o}`)}
              />
            </ChipsField>
            <ChipsField label={t("technologists.fields.languages")} required error={flag("languages")}>
              <ToggleChips
                label={t("technologists.fields.languages")}
                options={f?.languages ?? []}
                value={draft.languages}
                onChange={(v) => set("languages", v)}
                renderLabel={(o) => t(`technologists.language.${o}`)}
              />
            </ChipsField>
          </CardBody>
        </Card>

        <Card>
          <CardBody className="space-y-4">
            <p className="text-sm text-text-muted">{t("expert.profile.contactsHint")}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label={t("techRequest.contactPhone")}>
                {({ id }) => <Input id={id} type="tel" value={draft.contact_phone ?? ""} onChange={str("contact_phone")} />}
              </FormField>
              <FormField label={t("techRequest.contactEmail")}>
                {({ id }) => <Input id={id} type="email" value={draft.contact_email ?? ""} onChange={str("contact_email")} />}
              </FormField>
            </div>
          </CardBody>
        </Card>

        {missing.length > 0 ? <Alert tone="warning" title={t("expert.profile.incomplete")} /> : null}
        {save.isError || (submit.isError && missing.length === 0) || photo.isError ? (
          <Alert tone="danger" title={t("errors.generic")} />
        ) : null}
        {submit.isSuccess ? (
          <Alert tone="success" title={t("expert.profile.submitted")} />
        ) : save.isSuccess && !submit.isPending && !submit.isError ? (
          <Alert tone="success" title={t("expert.profile.saved")} />
        ) : null}

        <div className="flex flex-col gap-3 sm:flex-row">
          <Button
            variant="outline"
            size="lg"
            className="sm:flex-1"
            loading={save.isPending && !submit.isPending}
            disabled={busy || profile.status === "suspended"}
            onClick={() => {
              submit.reset();
              save.mutate(draft);
            }}
          >
            {t("expert.profile.save")}
          </Button>
          <Button
            size="lg"
            className="sm:flex-1"
            loading={submit.isPending}
            disabled={busy || profile.status === "suspended" || profile.status === "pending_review"}
            onClick={() => void saveAndSubmit()}
            data-testid="expert-submit"
          >
            {t("expert.profile.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ChipsField({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <FormField label={label} required={required} error={error}>
      {() => children}
    </FormField>
  );
}

function StatusBanner({ profile }: { profile: TechnologistOwnProfile }) {
  const { t } = useTranslation();
  switch (profile.status) {
    case "published":
      return <Alert tone="success" title={t("expert.status.published")} />;
    case "pending_review":
      return (
        <Alert tone="info" title={t("expert.status.pending")}>
          {profile.is_listed ? t("expert.status.listedMeanwhile") : null}
        </Alert>
      );
    case "rejected":
      return (
        <Alert tone="danger" title={t("expert.status.rejected")}>
          {profile.rejection_reason}
        </Alert>
      );
    case "suspended":
      return (
        <Alert tone="danger" title={t("expert.status.suspended")}>
          {profile.rejection_reason}
        </Alert>
      );
    default:
      return (
        <Alert tone={profile.is_listed ? "warning" : "info"} title={t(profile.is_listed ? "expert.status.unsentChanges" : "expert.status.draft")} />
      );
  }
}
