import { type FormEvent, useState } from "react";

import { useTranslation } from "react-i18next";

import { useCreateTechRequest, type TechRequestInput } from "@/entities/tech-request";
import { useTechFacets } from "@/entities/technologist";
import {
  Alert,
  Button,
  Card,
  CardBody,
  DateInput,
  FormField,
  Input,
  Select,
  Textarea,
  ToggleChips,
} from "@/shared/ui";

interface TechRequestFormProps {
  companyId: number;
  onCreated: (requestId: number) => void;
}

const EMPTY: TechRequestInput = {
  need_type: "",
  process: "",
  equipment: "",
  equipment_model: null,
  product: "",
  current_material: null,
  target_material: null,
  problem: "",
  capacity: null,
  capacity_unit: "kg_h",
  country: "UZ",
  city: null,
  urgency: "",
  needed_by: null,
  work_format: "",
  languages: ["ru"],
  budget_note: null,
};

/**
 * «Нужен технолог» — the brief's ten questions as one form.
 *
 * The closed sets (need, process, urgency, format, languages) come from the
 * API's facets, so the form and the matching rules can never disagree about
 * what a value may be. The same row is what the AI intake will fill later
 * (`source='ai'`), which is why the shape is flat and explicit rather than a
 * free-text brief.
 */
export function TechRequestForm({ companyId, onCreated }: TechRequestFormProps) {
  const { t } = useTranslation();
  const facets = useTechFacets();
  const create = useCreateTechRequest(companyId);
  const [draft, setDraft] = useState<TechRequestInput>(EMPTY);
  const [submitted, setSubmitted] = useState(false);

  const set = <K extends keyof TechRequestInput>(key: K, value: TechRequestInput[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const text = (key: keyof TechRequestInput) => (e: { target: { value: string } }) =>
    set(key, (e.target.value || null) as never);

  const missing = {
    need_type: !draft.need_type,
    process: !draft.process,
    equipment: !draft.equipment.trim(),
    product: !draft.product.trim(),
    problem: !draft.problem.trim(),
    country: !draft.country.trim(),
    urgency: !draft.urgency || (draft.urgency === "date" && !draft.needed_by),
    work_format: !draft.work_format,
  };
  const valid = !Object.values(missing).some(Boolean);
  const err = (key: keyof typeof missing) =>
    submitted && missing[key] ? t("techRequest.form.required") : null;

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    setSubmitted(true);
    if (!valid) return;
    create.mutate(
      {
        ...draft,
        capacity: draft.capacity || null,
        capacity_unit: draft.capacity ? draft.capacity_unit : null,
        needed_by: draft.urgency === "date" ? draft.needed_by : null,
      },
      { onSuccess: (request) => onCreated(request.id) },
    );
  }

  const f = facets.data;

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5" data-testid="tech-request-form">
      <Card>
        <CardBody className="space-y-5">
          <FormField label={t("techRequest.form.needType")} required error={err("need_type")}>
            {() => (
              <ToggleChips
                label={t("techRequest.form.needType")}
                single
                options={f?.need_types ?? []}
                value={draft.need_type ? [draft.need_type] : []}
                onChange={(v) => set("need_type", v[0] ?? "")}
                renderLabel={(o) => t(`technologists.need.${o}`)}
              />
            )}
          </FormField>

          <FormField label={t("techRequest.form.process")} required error={err("process")}>
            {() => (
              <ToggleChips
                label={t("techRequest.form.process")}
                single
                options={f?.processes ?? []}
                value={draft.process ? [draft.process] : []}
                onChange={(v) => set("process", v[0] ?? "")}
                renderLabel={(o) => t(`technologists.process.${o}`)}
              />
            )}
          </FormField>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t("techRequest.form.equipment")} required error={err("equipment")}>
              {({ id, invalid }) => (
                <Input
                  id={id}
                  invalid={invalid}
                  value={draft.equipment}
                  placeholder={t("techRequest.form.equipmentPlaceholder")}
                  onChange={(e) => set("equipment", e.target.value)}
                />
              )}
            </FormField>
            <FormField label={t("techRequest.form.equipmentModel")}>
              {({ id }) => (
                <Input id={id} value={draft.equipment_model ?? ""} onChange={text("equipment_model")} />
              )}
            </FormField>
          </div>

          <FormField label={t("techRequest.form.product")} required error={err("product")}>
            {({ id, invalid }) => (
              <Input
                id={id}
                invalid={invalid}
                value={draft.product}
                placeholder={t("techRequest.form.productPlaceholder")}
                onChange={(e) => set("product", e.target.value)}
              />
            )}
          </FormField>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              label={t("techRequest.form.currentMaterial")}
              hint={t("techRequest.form.currentMaterialHint")}
            >
              {({ id, describedBy }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  value={draft.current_material ?? ""}
                  placeholder="LLDPE C4"
                  onChange={text("current_material")}
                />
              )}
            </FormField>
            <FormField label={t("techRequest.form.targetMaterial")}>
              {({ id }) => (
                <Input
                  id={id}
                  value={draft.target_material ?? ""}
                  placeholder="HDPE / PP / …"
                  onChange={text("target_material")}
                />
              )}
            </FormField>
          </div>

          <FormField label={t("techRequest.form.problem")} required error={err("problem")}>
            {({ id, invalid }) => (
              <Textarea
                id={id}
                rows={4}
                aria-invalid={invalid || undefined}
                value={draft.problem}
                placeholder={t("techRequest.form.problemPlaceholder")}
                onChange={(e) => set("problem", e.target.value)}
              />
            )}
          </FormField>

          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_10rem]">
            <FormField label={t("techRequest.form.capacity")}>
              {({ id }) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  className="num"
                  value={draft.capacity ?? ""}
                  placeholder="500"
                  onChange={(e) => set("capacity", e.target.value.replace(",", ".") || null)}
                />
              )}
            </FormField>
            <FormField label={t("techRequest.form.capacityUnit")}>
              {({ id }) => (
                <Select
                  id={id}
                  value={draft.capacity_unit ?? "kg_h"}
                  onChange={(e) => set("capacity_unit", e.target.value)}
                  options={(f?.capacity_units ?? ["kg_h"]).map((u) => ({
                    value: u,
                    label: t(`technologists.capacityUnit.${u}`),
                  }))}
                />
              )}
            </FormField>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <FormField label={t("techRequest.form.country")} required error={err("country")}>
              {({ id, invalid }) => (
                <Input
                  id={id}
                  invalid={invalid}
                  maxLength={2}
                  className="num uppercase"
                  value={draft.country}
                  onChange={(e) => set("country", e.target.value.toUpperCase())}
                />
              )}
            </FormField>
            <FormField label={t("techRequest.form.city")}>
              {({ id }) => (
                <Input id={id} value={draft.city ?? ""} placeholder={t("techRequest.form.cityPlaceholder")} onChange={text("city")} />
              )}
            </FormField>
          </div>

          <FormField label={t("techRequest.form.urgency")} required error={err("urgency")}>
            {() => (
              <div className="space-y-3">
                <ToggleChips
                  label={t("techRequest.form.urgency")}
                  single
                  options={f?.urgencies ?? []}
                  value={draft.urgency ? [draft.urgency] : []}
                  onChange={(v) => set("urgency", v[0] ?? "")}
                  renderLabel={(o) => t(`technologists.urgency.${o}`)}
                />
                {draft.urgency === "date" ? (
                  <DateInput
                    aria-label={t("techRequest.form.neededBy")}
                    pickerLabel={t("techRequest.form.neededBy")}
                    value={draft.needed_by ?? ""}
                    onChange={(e) => set("needed_by", e.target.value || null)}
                  />
                ) : null}
              </div>
            )}
          </FormField>

          <FormField label={t("techRequest.form.workFormat")} required error={err("work_format")}>
            {() => (
              <ToggleChips
                label={t("techRequest.form.workFormat")}
                single
                options={f?.request_formats ?? []}
                value={draft.work_format ? [draft.work_format] : []}
                onChange={(v) => set("work_format", v[0] ?? "")}
                renderLabel={(o) => t(`technologists.format.${o}`)}
              />
            )}
          </FormField>

          <FormField label={t("techRequest.form.languages")}>
            {() => (
              <ToggleChips
                label={t("techRequest.form.languages")}
                options={f?.languages ?? []}
                value={draft.languages}
                onChange={(v) => set("languages", v)}
                renderLabel={(o) => t(`technologists.language.${o}`)}
              />
            )}
          </FormField>

          <FormField label={t("techRequest.form.budget")} hint={t("techRequest.form.budgetHint")}>
            {({ id, describedBy }) => (
              <Input id={id} aria-describedby={describedBy} value={draft.budget_note ?? ""} onChange={text("budget_note")} />
            )}
          </FormField>
        </CardBody>
      </Card>

      {create.error ? (
        <Alert
          tone="danger"
          title={
            // 403 is `company_not_verified` — the one refusal a valid form gets.
            create.error.status === 403
              ? t("techRequest.form.notVerified")
              : t("errors.generic")
          }
        />
      ) : null}

      <Button type="submit" size="lg" fullWidth loading={create.isPending}>
        {t("techRequest.form.submit")}
      </Button>
    </form>
  );
}
