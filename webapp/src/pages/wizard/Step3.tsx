/**
 * C-04 — Step 3: Contact information (of 4).
 *
 * Company, contact person, phone (required), legal address (IMG_0046
 * "Контактная информация"). Telegram is taken automatically from initData, so it
 * is shown as a read-only note rather than a field. Phone is the one required field.
 * BackButton → Step 2, MainButton "Далее" → Step 4 (enabled once phone is filled).
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import StepIndicator from "../../components/StepIndicator";
import FieldGroup from "../../components/FieldGroup";
import { mainButton, backButton, impactLight } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";

const fieldStyle = {
  display: "block",
  width: "100%",
  minHeight: "44px",
  padding: "10px 12px",
  borderRadius: "var(--r-md)",
  backgroundColor: "var(--surface)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontSize: "14px",
  boxSizing: "border-box" as const,
};

export default function Step3() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const store = useWizardStore();

  const [companyName, setCompanyName] = useState(store.company_name);
  const [contactName, setContactName] = useState(store.contact_name);
  const [phone, setPhone] = useState(store.phone);
  const [legalAddress, setLegalAddress] = useState(store.legal_address);

  const phoneValid = phone.trim() !== "";

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  function saveToStore() {
    store.setField("company_name", companyName);
    store.setField("contact_name", contactName);
    store.setField("phone", phone);
    store.setField("legal_address", legalAddress);
  }

  useEffect(() => {
    backButton.show();
    const cleanupBack = backButton.onClick(() => {
      saveToStore();
      navigate("/request/step/2");
    });
    return () => {
      cleanupBack();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, companyName, contactName, phone, legalAddress]);

  useEffect(() => {
    mainButton.setText(t("wizard.next"));
    mainButton.show();
    if (phoneValid) {
      mainButton.enable();
    } else {
      mainButton.disable();
    }
  }, [t, phoneValid]);

  useEffect(() => {
    const cleanupMain = mainButton.onClick(() => {
      if (!phoneValid) return;
      saveToStore();
      impactLight();
      navigate("/request/step/4");
    });
    return () => {
      cleanupMain();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, phoneValid, companyName, contactName, phone, legalAddress]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator current={3} total={4} subtitle={t("wizard.stepOf", { current: 3, total: 4 })} />
      </div>

      <h2
        ref={headingRef}
        tabIndex={-1}
        style={{ margin: "0 0 20px", fontSize: "17px", fontWeight: 600, color: "var(--text)", outline: "none" }}
      >
        {t("wizard.step3.title")}
      </h2>

      <form onSubmit={(e) => e.preventDefault()}>
        <FieldGroup htmlFor="company_name" label={t("wizard.companyName")}>
          <input id="company_name" type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder={t("wizard.companyPlaceholder")} style={fieldStyle} />
        </FieldGroup>

        <FieldGroup htmlFor="contact_name" label={t("wizard.contactName")}>
          <input id="contact_name" type="text" value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder={t("wizard.contactPlaceholder")} style={fieldStyle} />
        </FieldGroup>

        <FieldGroup htmlFor="phone" label={t("wizard.phone")} required error={phoneValid ? undefined : t("error.required")}>
          <input id="phone" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+998 __ ___ __ __" style={fieldStyle} />
        </FieldGroup>

        <FieldGroup htmlFor="legal_address" label={t("wizard.legalAddress")}>
          <input id="legal_address" type="text" value={legalAddress} onChange={(e) => setLegalAddress(e.target.value)} placeholder={t("wizard.legalAddressPlaceholder")} style={fieldStyle} />
        </FieldGroup>

        <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "-4px" }}>{t("wizard.telegramAuto")}</p>

        <button
          type="button"
          disabled={!phoneValid}
          onClick={() => {
            if (!phoneValid) return;
            saveToStore();
            impactLight();
            navigate("/request/step/4");
          }}
          style={{
            display: "block",
            width: "100%",
            minHeight: "44px",
            padding: "12px 20px",
            borderRadius: "var(--r-md)",
            backgroundColor: phoneValid ? "var(--green)" : "var(--chip-neutral-bg)",
            color: phoneValid ? "var(--green-on)" : "var(--text-muted)",
            border: "none",
            fontSize: "16px",
            fontWeight: 600,
            cursor: phoneValid ? "pointer" : "not-allowed",
            boxSizing: "border-box",
            marginTop: "12px",
          }}
        >
          {t("wizard.next")}
        </button>
      </form>
    </div>
  );
}
