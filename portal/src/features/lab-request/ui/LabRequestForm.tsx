import { useState } from "react";

import { useTranslation } from "react-i18next";

import { useCreateLabRequest } from "@/entities/lab-request";
import {
  LAB_METHODS,
  LAB_PURPOSES,
  LAB_STUDY_TYPES,
} from "@/features/company-wizard/model/constants";
import {
  Alert,
  Button,
  Checkbox,
  DateInput,
  FlaskIcon,
  FormField,
  Input,
  Radio,
  Select,
  Stepper,
  Textarea,
} from "@/shared/ui";

interface LabRequestFormProps {
  /** The buyer's acting company. */
  companyId: number;
  onSent: (requestId: number) => void;
}

const STEP_SUBJECT = 1;
const STEP_DETAILS = 2;

/**
 * «Новая заявка» → «Данные для заявки» — the mockup's two sheets.
 *
 * A wizard where the logistics form is one screen, and the reason is only that
 * this one is twice the size: thirteen fields across two clearly separate
 * questions (what to test / who is asking and by when). Splitting the carrier's
 * seven would have been ceremony; not splitting these would be a wall.
 *
 * Local state, no zustand draft: both steps live in this component, so there is
 * no navigation for a draft to survive.
 *
 * No laboratory is chosen. The request is BROADCAST — a buyer with material to
 * test does not know which of ten labs runs that method, so they state the job
 * and the labs come to them.
 */
export function LabRequestForm({ companyId, onSent }: LabRequestFormProps) {
  const { t } = useTranslation();
  const create = useCreateLabRequest();
  const [step, setStep] = useState(STEP_SUBJECT);
  const [touched, setTouched] = useState(false);

  const [form, setForm] = useState({
    product_text: "",
    grade_text: "",
    study_type: "",
    methods: [] as string[],
    sample_qty: "",
    comment: "",
    purpose: "",
    is_urgent: false,
    desired_date: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
  });

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const toggleMethod = (key: string) =>
    setForm((f) => ({
      ...f,
      methods: f.methods.includes(key)
        ? f.methods.filter((m) => m !== key)
        : [...f.methods, key],
    }));

  const productOk = form.product_text.trim().length > 0;
  const methodsOk = form.methods.length > 0;
  const subjectOk = productOk && methodsOk;

  const error = create.error ? t("errors.generic") : null;

  const steps = [
    { id: STEP_SUBJECT, label: t("labRequest.stepSubject") },
    { id: STEP_DETAILS, label: t("labRequest.stepDetails") },
  ];

  function next(): void {
    setTouched(true);
    if (!subjectOk) return;
    setTouched(false);
    setStep(STEP_DETAILS);
  }

  function submit(): void {
    setTouched(true);
    if (!subjectOk) return;
    create.mutate(
      {
        company_id: companyId,
        product_text: form.product_text.trim(),
        grade_text: form.grade_text.trim() || null,
        study_type: form.study_type || null,
        methods: form.methods,
        sample_qty: form.sample_qty.trim() || null,
        comment: form.comment.trim() || null,
        purpose: form.purpose || null,
        is_urgent: form.is_urgent,
        desired_date: form.desired_date || null,
        contact_name: form.contact_name.trim() || null,
        contact_email: form.contact_email.trim() || null,
        contact_phone: form.contact_phone.trim() || null,
      },
      { onSuccess: (created) => onSent(created.id) },
    );
  }

  return (
    <div className="space-y-6" data-testid="lab-request-form">
      <div className="flex items-start gap-3">
        <span className="shrink-0 text-brand">
          <FlaskIcon size={32} />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-tight text-text">
            {t("labRequest.heroTitle")}
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-text-muted">
            {t("labRequest.heroBody")}
          </p>
        </div>
      </div>

      <Stepper
        steps={steps}
        current={step}
        completedIds={step === STEP_DETAILS ? [STEP_SUBJECT] : []}
        variant="stacked"
      />

      {step === STEP_SUBJECT ? (
        <section className="space-y-4">
          <FormField
            label={t("labRequest.product")}
            required
            error={touched && !productOk ? t("labRequest.errors.productRequired") : null}
          >
            {({ id, invalid }) => (
              <Input
                id={id}
                value={form.product_text}
                invalid={invalid}
                placeholder={t("labRequest.productPlaceholder")}
                onChange={(e) => set({ product_text: e.target.value })}
              />
            )}
          </FormField>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t("labRequest.grade")}>
              {({ id }) => (
                <Input
                  id={id}
                  value={form.grade_text}
                  onChange={(e) => set({ grade_text: e.target.value })}
                />
              )}
            </FormField>
            <FormField label={t("labRequest.studyType")}>
              {({ id }) => (
                <Select
                  id={id}
                  value={form.study_type}
                  placeholder={t("labRequest.studyTypePlaceholder")}
                  options={LAB_STUDY_TYPES.map((key) => ({
                    value: key,
                    label: t(`labRequest.studyTypes.${key}`),
                  }))}
                  onChange={(e) => set({ study_type: e.target.value })}
                />
              )}
            </FormField>
          </div>

          <FormField
            label={t("labRequest.methods")}
            required
            hint={t("labRequest.methodsHint")}
            error={touched && !methodsOk ? t("labRequest.errors.methodsRequired") : null}
          >
            {() => (
              <div className="grid gap-2 sm:grid-cols-2">
                {LAB_METHODS.map((key) => (
                  <Checkbox
                    key={key}
                    label={t(`labRequest.methodOptions.${key}`)}
                    checked={form.methods.includes(key)}
                    onChange={() => toggleMethod(key)}
                    data-testid={`lab-method-${key}`}
                  />
                ))}
              </div>
            )}
          </FormField>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t("labRequest.sampleQty")} hint={t("labRequest.sampleQtyHint")}>
              {({ id }) => (
                <Input
                  id={id}
                  value={form.sample_qty}
                  placeholder="1 кг"
                  onChange={(e) => set({ sample_qty: e.target.value })}
                />
              )}
            </FormField>
          </div>

          <FormField label={t("labRequest.comment")}>
            {({ id }) => (
              <Textarea
                id={id}
                rows={2}
                value={form.comment}
                placeholder={t("labRequest.commentPlaceholder")}
                onChange={(e) => set({ comment: e.target.value })}
              />
            )}
          </FormField>

          <Button fullWidth size="lg" onClick={next} data-testid="lab-request-next">
            {t("common.next")}
          </Button>
        </section>
      ) : (
        <section className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t("labRequest.contactName")}>
              {({ id }) => (
                <Input
                  id={id}
                  value={form.contact_name}
                  onChange={(e) => set({ contact_name: e.target.value })}
                />
              )}
            </FormField>
            <FormField label={t("labRequest.contactEmail")}>
              {({ id }) => (
                <Input
                  id={id}
                  type="email"
                  value={form.contact_email}
                  onChange={(e) => set({ contact_email: e.target.value })}
                />
              )}
            </FormField>
          </div>

          <FormField label={t("labRequest.contactPhone")} hint={t("labRequest.contactPhoneHint")}>
            {({ id }) => (
              <Input
                id={id}
                inputMode="tel"
                value={form.contact_phone}
                onChange={(e) => set({ contact_phone: e.target.value })}
              />
            )}
          </FormField>

          <FormField label={t("labRequest.purpose")}>
            {({ id }) => (
              <Select
                id={id}
                value={form.purpose}
                placeholder={t("labRequest.purposePlaceholder")}
                options={LAB_PURPOSES.map((key) => ({
                  value: key,
                  label: t(`labRequest.purposes.${key}`),
                }))}
                onChange={(e) => set({ purpose: e.target.value })}
              />
            )}
          </FormField>

          <FormField label={t("labRequest.urgent")}>
            {() => (
              <div className="flex gap-4">
                <Radio
                  name="lab-urgent"
                  label={t("common.yes")}
                  checked={form.is_urgent}
                  onChange={() => set({ is_urgent: true })}
                />
                <Radio
                  name="lab-urgent"
                  label={t("common.no")}
                  checked={!form.is_urgent}
                  onChange={() => set({ is_urgent: false })}
                />
              </div>
            )}
          </FormField>

          <FormField label={t("labRequest.desiredDate")}>
            {({ id }) => (
              <DateInput
                id={id}
                value={form.desired_date}
                pickerLabel={t("labRequest.desiredDate")}
                onChange={(e) => set({ desired_date: e.target.value })}
              />
            )}
          </FormField>

          {error ? (
            <Alert tone="danger" title={t("errors.generic")} data-testid="lab-request-error">
              {error}
            </Alert>
          ) : null}

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="outline" fullWidth onClick={() => setStep(STEP_SUBJECT)}>
              {t("common.back")}
            </Button>
            <Button
              fullWidth
              size="lg"
              loading={create.isPending}
              onClick={submit}
              data-testid="lab-request-submit"
            >
              {t("labRequest.submit")}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}
