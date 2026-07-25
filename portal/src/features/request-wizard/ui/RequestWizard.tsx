import { useState } from "react";

import { useTranslation } from "react-i18next";

import { useCreateRequest, type RequestPayload } from "@/entities/request";
import { INCOTERMS } from "@/shared/config";
import {
  Alert,
  Button,
  FormField,
  Input,
  Select,
  Stepper,
  Textarea,
  type Step,
} from "@/shared/ui";

const URGENCIES = ["low", "medium", "high"] as const;

interface Draft {
  product_text: string;
  grade_text: string;
  polymer_type: string;
  volume: string;
  volume_unit: string;
  target_price: string;
  currency: string;
  incoterms: string;
  destination_country: string;
  port_or_city: string;
  desired_date: string;
  validity_days: string;
  urgency: string;
  comment: string;
  company_name: string;
  contact_name: string;
  phone: string;
  legal_address: string;
}

const EMPTY: Draft = {
  product_text: "",
  grade_text: "",
  polymer_type: "",
  volume: "",
  volume_unit: "MT",
  target_price: "",
  currency: "USD",
  incoterms: "unknown",
  destination_country: "UZ",
  port_or_city: "",
  desired_date: "",
  validity_days: "30",
  urgency: "medium",
  comment: "",
  company_name: "",
  contact_name: "",
  phone: "",
  legal_address: "",
};

interface RequestWizardProps {
  companyId: number;
  companyName: string;
  onCreated: (requestId: number) => void;
}

export function RequestWizard({ companyId, companyName, onCreated }: RequestWizardProps) {
  const { t } = useTranslation();
  const create = useCreateRequest(companyId);
  const [step, setStep] = useState(1);
  const [d, setD] = useState<Draft>({ ...EMPTY, company_name: companyName });

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setD((prev) => ({ ...prev, [key]: value }));

  const steps: Step[] = [
    { id: 1, label: t("requestWizard.step.product") },
    { id: 2, label: t("requestWizard.step.specs") },
    { id: 3, label: t("requestWizard.step.delivery") },
    { id: 4, label: t("requestWizard.step.contacts") },
  ];

  // Minimum to submit (mirror backend RequestCreate): a product, positive volume,
  // and at least one of grade / polymer.
  const step1Valid =
    d.product_text.trim() !== "" &&
    (d.grade_text.trim() !== "" || d.polymer_type.trim() !== "");
  const step2Valid = Number(d.volume) > 0;

  function submit() {
    const payload: RequestPayload = {
      company_id: companyId,
      product_text: d.product_text.trim() || null,
      grade_text: d.grade_text.trim() || null,
      polymer_type: d.polymer_type.trim() || null,
      volume: d.volume,
      volume_unit: d.volume_unit,
      target_price: d.target_price.trim() || null,
      currency: d.currency,
      incoterms: d.incoterms,
      destination_country: d.destination_country.trim().toUpperCase() || "UZ",
      port_or_city: d.port_or_city.trim() || null,
      desired_date: d.desired_date || null,
      validity_days: Number(d.validity_days) || 30,
      urgency: d.urgency,
      comment: d.comment.trim() || null,
      company_name: d.company_name.trim() || null,
      contact_name: d.contact_name.trim() || null,
      phone: d.phone.trim() || null,
      legal_address: d.legal_address.trim() || null,
    };
    create.mutate(payload, { onSuccess: (r) => onCreated(r.id) });
  }

  return (
    <div className="space-y-6">
      <Stepper steps={steps} current={step} />

      {create.isError ? <Alert tone="danger">{t("requestWizard.submitFailed")}</Alert> : null}

      {step === 1 ? (
        <div className="space-y-4">
          <FormField label={t("requestWizard.product")} required>
            {({ id }) => (
              <Input id={id} value={d.product_text} onChange={(e) => set("product_text", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.grade")}>
            {({ id }) => (
              <Input id={id} value={d.grade_text} onChange={(e) => set("grade_text", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.polymer")}>
            {({ id }) => (
              <Input id={id} value={d.polymer_type} onChange={(e) => set("polymer_type", e.target.value)} />
            )}
          </FormField>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={t("requestWizard.volume")} required>
            {({ id }) => (
              <Input id={id} inputMode="decimal" value={d.volume} onChange={(e) => set("volume", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.unit")}>
            {({ id }) => (
              <Input id={id} value={d.volume_unit} onChange={(e) => set("volume_unit", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.targetPrice")}>
            {({ id }) => (
              <Input id={id} inputMode="decimal" value={d.target_price} onChange={(e) => set("target_price", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.currency")}>
            {({ id }) => (
              <Input id={id} value={d.currency} onChange={(e) => set("currency", e.target.value)} maxLength={3} />
            )}
          </FormField>
          <FormField label={t("requestWizard.incoterms")} className="sm:col-span-2">
            {({ id }) => (
              <Select
                id={id}
                value={d.incoterms}
                onChange={(e) => set("incoterms", e.target.value)}
                options={INCOTERMS.map((i) => ({ value: i, label: i }))}
              />
            )}
          </FormField>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={t("requestWizard.country")}>
            {({ id }) => (
              <Input id={id} value={d.destination_country} onChange={(e) => set("destination_country", e.target.value)} maxLength={2} />
            )}
          </FormField>
          <FormField label={t("requestWizard.city")}>
            {({ id }) => (
              <Input id={id} value={d.port_or_city} onChange={(e) => set("port_or_city", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.desiredDate")}>
            {({ id }) => (
              <Input id={id} type="date" value={d.desired_date} onChange={(e) => set("desired_date", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.validityDays")}>
            {({ id }) => (
              <Input id={id} inputMode="numeric" value={d.validity_days} onChange={(e) => set("validity_days", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.urgency")} className="sm:col-span-2">
            {({ id }) => (
              <Select
                id={id}
                value={d.urgency}
                onChange={(e) => set("urgency", e.target.value)}
                options={URGENCIES.map((u) => ({ value: u, label: t(`requestWizard.urgencyOpt.${u}`) }))}
              />
            )}
          </FormField>
        </div>
      ) : null}

      {step === 4 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={t("requestWizard.companyName")}>
            {({ id }) => (
              <Input id={id} value={d.company_name} onChange={(e) => set("company_name", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.contactName")}>
            {({ id }) => (
              <Input id={id} value={d.contact_name} onChange={(e) => set("contact_name", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.phone")}>
            {({ id }) => (
              <Input id={id} value={d.phone} onChange={(e) => set("phone", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.legalAddress")}>
            {({ id }) => (
              <Input id={id} value={d.legal_address} onChange={(e) => set("legal_address", e.target.value)} />
            )}
          </FormField>
          <FormField label={t("requestWizard.comment")} className="sm:col-span-2">
            {({ id }) => (
              <Textarea id={id} rows={3} value={d.comment} onChange={(e) => set("comment", e.target.value)} />
            )}
          </FormField>
        </div>
      ) : null}

      <div className="flex items-center justify-between pt-2">
        <Button variant="ghost" disabled={step === 1} onClick={() => setStep((s) => s - 1)}>
          {t("common.back")}
        </Button>
        {step < 4 ? (
          <Button
            disabled={(step === 1 && !step1Valid) || (step === 2 && !step2Valid)}
            onClick={() => setStep((s) => s + 1)}
          >
            {t("common.next")}
          </Button>
        ) : (
          <Button
            disabled={!step1Valid || !step2Valid || create.isPending}
            onClick={submit}
          >
            {create.isPending ? t("common.saving") : t("requestWizard.submit")}
          </Button>
        )}
      </div>
    </div>
  );
}
