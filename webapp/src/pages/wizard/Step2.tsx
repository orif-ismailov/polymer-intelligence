/**
 * C-03 — Step 2: Delivery terms.
 *
 * All fields are optional (D-02) — advancing is always permitted.
 * BackButton → Step 1 (state preserved via wizardStore).
 * MainButton text="Далее" → store → Step 3.
 * Focus moves to step heading on mount (accessibility).
 */

import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";

import StepIndicator from "../../components/StepIndicator";
import FieldGroup from "../../components/FieldGroup";
import SelectField from "../../components/SelectField";
import { mainButton, backButton, impactLight } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";

// PriceBasis values (mirrors backend PriceBasis enum)
const INCOTERMS_BASE = [
  { value: "EXW", label: "EXW" },
  { value: "FCA", label: "FCA" },
  { value: "FAS", label: "FAS" },
  { value: "FOB", label: "FOB" },
  { value: "CFR", label: "CFR" },
  { value: "CIF", label: "CIF" },
  { value: "CPT", label: "CPT" },
  { value: "CIP", label: "CIP" },
  { value: "DAP", label: "DAP" },
  { value: "DPU", label: "DPU" },
  { value: "DDP", label: "DDP" },
];

const CURRENCY_OPTIONS = [
  { value: "USD", label: "USD" },
  { value: "EUR", label: "EUR" },
  { value: "UZS", label: "UZS" },
  { value: "RUB", label: "RUB" },
];

interface Step2Fields {
  target_price: string;
  currency: string;
  incoterms: string;
  destination_country: string;
  port_or_city: string;
  desired_date: string;
  validity_days: string;
}

const fieldStyle = {
  display: "block",
  width: "100%",
  minHeight: "44px",
  padding: "10px 12px",
  borderRadius: "8px",
  backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
  color: "var(--tg-theme-text-color, #f8fafc)",
  border: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
  fontSize: "14px",
  fontFamily: "system-ui, sans-serif",
  boxSizing: "border-box" as const,
};

export default function Step2() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const store = useWizardStore();

  const { register, getValues } = useForm<Step2Fields>({
    defaultValues: {
      target_price: store.target_price,
      currency: store.currency,
      incoterms: store.incoterms,
      destination_country: store.destination_country,
      port_or_city: store.port_or_city,
      desired_date: store.desired_date,
      validity_days: store.validity_days,
    },
  });

  // Focus heading on mount
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // BackButton → Step 1 (state preserved)
  useEffect(() => {
    backButton.show();
    const cleanupBack = backButton.onClick(() => {
      saveToStore();
      navigate("/request/step/1");
    });
    return () => { cleanupBack(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate]);

  // MainButton — always enabled (all fields optional)
  useEffect(() => {
    mainButton.setText(t("wizard.next"));
    mainButton.show();
    mainButton.enable();
  }, [t]);

  // MainButton click → save + navigate
  useEffect(() => {
    const cleanupMain = mainButton.onClick(() => {
      saveToStore();
      impactLight();
      navigate("/request/step/3");
    });
    return () => { cleanupMain(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate]);

  function saveToStore() {
    const data = getValues();
    store.setField("target_price", data.target_price);
    store.setField("currency", data.currency);
    store.setField("incoterms", data.incoterms);
    store.setField("destination_country", data.destination_country);
    store.setField("port_or_city", data.port_or_city);
    store.setField("desired_date", data.desired_date);
    store.setField("validity_days", data.validity_days);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
        color: "var(--tg-theme-text-color, #f8fafc)",
        padding: "16px",
      }}
    >
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator current={2} total={4} />
      </div>

      <h2
        ref={headingRef}
        tabIndex={-1}
        style={{
          margin: "0 0 24px",
          fontSize: "18px",
          fontWeight: 600,
          color: "var(--tg-theme-text-color, #f8fafc)",
          outline: "none",
        }}
      >
        {t("wizard.step2.title")}
      </h2>

      <form onSubmit={(e) => e.preventDefault()}>
        {/* Target price */}
        <FieldGroup htmlFor="target_price" label={t("wizard.targetPrice")}>
          <input
            id="target_price"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            placeholder={t("wizard.pricePlaceholder")}
            style={fieldStyle}
            {...register("target_price")}
          />
        </FieldGroup>

        {/* Currency */}
        <FieldGroup htmlFor="currency" label={t("wizard.currency")}>
          <SelectField
            id="currency"
            options={CURRENCY_OPTIONS}
            defaultValue={store.currency}
            {...register("currency")}
          />
        </FieldGroup>

        {/* Incoterms */}
        <FieldGroup htmlFor="incoterms" label={t("wizard.incoterms")}>
          <SelectField
            id="incoterms"
            options={[
              { value: "unknown", label: t("wizard.incotermsNone") },
              ...INCOTERMS_BASE,
            ]}
            defaultValue={store.incoterms}
            {...register("incoterms")}
          />
        </FieldGroup>

        {/* Destination country */}
        <FieldGroup htmlFor="destination_country" label={t("wizard.destinationCountry")}>
          <input
            id="destination_country"
            type="text"
            defaultValue={store.destination_country}
            style={fieldStyle}
            {...register("destination_country")}
          />
        </FieldGroup>

        {/* Port / city */}
        <FieldGroup htmlFor="port_or_city" label={t("wizard.portOrCity")}>
          <input
            id="port_or_city"
            type="text"
            placeholder={t("wizard.portPlaceholder")}
            style={fieldStyle}
            {...register("port_or_city")}
          />
        </FieldGroup>

        {/* Desired date */}
        <FieldGroup htmlFor="desired_date" label={t("wizard.desiredDate")}>
          <input
            id="desired_date"
            type="date"
            style={fieldStyle}
            {...register("desired_date")}
          />
        </FieldGroup>

        {/* Validity days */}
        <FieldGroup htmlFor="validity_days" label={t("wizard.validityDays")}>
          <input
            id="validity_days"
            type="number"
            inputMode="numeric"
            min="1"
            placeholder="30"
            style={fieldStyle}
            {...register("validity_days")}
          />
        </FieldGroup>

        {/* Fallback button for non-Telegram (dev) */}
        <button
          type="button"
          onClick={() => {
            saveToStore();
            impactLight();
            navigate("/request/step/3");
          }}
          style={{
            display: "block",
            width: "100%",
            minHeight: "44px",
            padding: "12px 20px",
            borderRadius: "8px",
            backgroundColor: "var(--tg-theme-button-color, #10b981)",
            color: "var(--tg-theme-button-text-color, #ffffff)",
            border: "none",
            fontSize: "14px",
            fontWeight: 600,
            cursor: "pointer",
            boxSizing: "border-box",
            marginTop: "8px",
          }}
        >
          {t("wizard.next")}
        </button>
      </form>
    </div>
  );
}
