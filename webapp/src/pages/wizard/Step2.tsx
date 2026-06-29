/**
 * C-03 — Step 2: Delivery terms (of 4).
 *
 * Availability + urgency as tappable radio cards (IMG_0044 "Условия поставки"),
 * plus delivery city and desired date. All optional — advancing is always allowed.
 * BackButton → Step 1, MainButton "Далее" → Step 3.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import StepIndicator from "../../components/StepIndicator";
import FieldGroup from "../../components/FieldGroup";
import RadioCard from "../../components/RadioCard";
import { mainButton, backButton, impactLight } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";

const AVAILABILITY = ["tashkent", "uzbekistan", "import", "any"] as const;
const URGENCY = ["high", "medium", "low"] as const;

const fieldStyle = {
  display: "block",
  width: "100%",
  minHeight: "44px",
  padding: "10px 12px",
  borderRadius: "var(--r-md)",
  backgroundColor: "var(--surface)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontSize: "16px",
  boxSizing: "border-box" as const,
};
const groupLabel = {
  display: "block",
  margin: "0 0 10px",
  fontSize: "13px",
  fontWeight: 600,
  color: "var(--text-muted)",
} as const;

export default function Step2() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const store = useWizardStore();

  const [availability, setAvailability] = useState(store.availability);
  const [urgency, setUrgency] = useState(store.urgency);
  const [city, setCity] = useState(store.port_or_city);
  const [date, setDate] = useState(store.desired_date);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  function saveToStore() {
    store.setField("availability", availability);
    store.setField("urgency", urgency);
    store.setField("port_or_city", city);
    store.setField("desired_date", date);
  }

  useEffect(() => {
    backButton.show();
    const cleanupBack = backButton.onClick(() => {
      saveToStore();
      navigate("/request/step/1");
    });
    return () => {
      cleanupBack();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, availability, urgency, city, date]);

  useEffect(() => {
    mainButton.setText(t("wizard.next"));
    mainButton.show();
    mainButton.enable();
  }, [t]);

  useEffect(() => {
    const cleanupMain = mainButton.onClick(() => {
      saveToStore();
      impactLight();
      navigate("/request/step/3");
    });
    return () => {
      cleanupMain();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, availability, urgency, city, date]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator current={2} total={4} subtitle={t("wizard.stepOf", { current: 2, total: 4 })} />
      </div>

      <h2
        ref={headingRef}
        tabIndex={-1}
        style={{ margin: "0 0 20px", fontSize: "17px", fontWeight: 600, color: "var(--text)", outline: "none" }}
      >
        {t("wizard.step2.title")}
      </h2>

      <form onSubmit={(e) => e.preventDefault()}>
        <div style={{ marginBottom: "20px" }}>
          <span style={groupLabel}>{t("wizard.availability")}</span>
          {AVAILABILITY.map((a) => (
            <RadioCard
              key={a}
              selected={availability === a}
              label={t(`wizard.availabilityOpt.${a}`)}
              description={t(`wizard.availabilityDesc.${a}`, { defaultValue: "" }) || undefined}
              onClick={() => setAvailability(a)}
            />
          ))}
        </div>

        <div style={{ marginBottom: "20px" }}>
          <span style={groupLabel}>{t("wizard.urgency")}</span>
          {URGENCY.map((u) => (
            <RadioCard
              key={u}
              selected={urgency === u}
              label={t(`wizard.urgencyOpt.${u}`)}
              onClick={() => setUrgency(u)}
            />
          ))}
        </div>

        <FieldGroup htmlFor="port_or_city" label={t("wizard.deliveryCity")}>
          <input id="port_or_city" type="text" value={city} onChange={(e) => setCity(e.target.value)} placeholder={t("wizard.portPlaceholder")} style={fieldStyle} />
        </FieldGroup>

        <FieldGroup htmlFor="desired_date" label={t("wizard.desiredDate")}>
          <input id="desired_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} style={fieldStyle} />
        </FieldGroup>

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
            borderRadius: "var(--r-md)",
            backgroundColor: "var(--green)",
            color: "var(--green-on)",
            border: "none",
            fontSize: "16px",
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
