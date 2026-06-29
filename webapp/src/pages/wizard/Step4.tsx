/**
 * C-05 — Step 4: Additional information (of 4).
 *
 * Desired price (+currency), comment, and file attachments / TDS (IMG_0046
 * "Дополнительная информация"). All optional. MainButton label is "Отправить" and
 * navigates to Confirm, which performs the POST. BackButton → Step 3.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";

import StepIndicator from "../../components/StepIndicator";
import FieldGroup from "../../components/FieldGroup";
import SelectField from "../../components/SelectField";
import FileUploader from "../../components/FileUploader";
import HintBanner from "../../components/HintBanner";
import { mainButton, backButton } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";

const CURRENCY_OPTIONS = [
  { value: "USD", label: "USD" },
  { value: "EUR", label: "EUR" },
  { value: "UZS", label: "UZS" },
  { value: "RUB", label: "RUB" },
];

interface Step4Fields {
  target_price: string;
  currency: string;
}

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

export default function Step4() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const store = useWizardStore();
  const [comment, setComment] = useState(store.comment);

  const { register, getValues } = useForm<Step4Fields>({
    defaultValues: { target_price: store.target_price, currency: store.currency },
  });

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  function saveToStore() {
    const data = getValues();
    store.setField("target_price", data.target_price);
    store.setField("currency", data.currency);
    store.setField("comment", comment);
  }

  useEffect(() => {
    backButton.show();
    const cleanupBack = backButton.onClick(() => {
      saveToStore();
      navigate("/request/step/3");
    });
    return () => {
      cleanupBack();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, comment]);

  useEffect(() => {
    mainButton.setText(t("wizard.submitRequest"));
    mainButton.show();
    mainButton.enable();
  }, [t]);

  useEffect(() => {
    const cleanupMain = mainButton.onClick(() => {
      saveToStore();
      navigate("/request/confirm");
    });
    return () => {
      cleanupMain();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, comment]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator current={4} total={4} subtitle={t("wizard.stepOf", { current: 4, total: 4 })} />
      </div>

      <h2
        ref={headingRef}
        tabIndex={-1}
        style={{ margin: "0 0 20px", fontSize: "17px", fontWeight: 600, color: "var(--text)", outline: "none" }}
      >
        {t("wizard.step4.title")}
      </h2>

      {/* "Ваша заявка" recap (IMG_0044 step 4 summary box) */}
      <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "12px 14px", marginBottom: "20px" }}>
        <p style={{ margin: "0 0 8px", fontSize: "13px", fontWeight: 700, color: "var(--text-muted)" }}>
          {t("wizard.summary")}
        </p>
        {[
          [t("wizard.product"), store.grade_text || store.product_text || "—"],
          [t("wizard.volume"), `${store.volume || "—"} ${store.volume_unit}`],
          [t("wizard.deliveryCity"), store.port_or_city || "—"],
          [t("wizard.urgency"), store.urgency ? t(`wizard.urgencyOpt.${store.urgency}`) : "—"],
        ].map(([k, v]) => (
          <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "3px 0", fontSize: "13px" }}>
            <span style={{ color: "var(--text-muted)" }}>{k}</span>
            <span style={{ color: "var(--text)", fontWeight: 600, textAlign: "right" }}>{v}</span>
          </div>
        ))}
      </div>

      <form onSubmit={(e) => e.preventDefault()}>
        <FieldGroup htmlFor="target_price" label={t("wizard.desiredPrice")}>
          <input id="target_price" type="number" inputMode="decimal" min="0" step="any" placeholder={t("wizard.pricePlaceholder")} style={fieldStyle} {...register("target_price")} />
        </FieldGroup>

        <FieldGroup htmlFor="currency" label={t("wizard.currency")}>
          <SelectField id="currency" options={CURRENCY_OPTIONS} defaultValue={store.currency} {...register("currency")} />
        </FieldGroup>

        <FieldGroup htmlFor="comment" label={t("wizard.comment")}>
          <textarea
            id="comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={t("wizard.commentPlaceholder")}
            rows={4}
            style={{ ...fieldStyle, minHeight: "100px", resize: "vertical" }}
          />
        </FieldGroup>

        <FieldGroup htmlFor="file-uploader-input" label={t("wizard.attachTds")}>
          <FileUploader />
        </FieldGroup>

        <HintBanner tone="ok">{t("wizard.dataProtected")}</HintBanner>

        <button
          type="button"
          onClick={() => {
            saveToStore();
            navigate("/request/confirm");
          }}
          style={{
            display: "block",
            width: "100%",
            minHeight: "48px",
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
          {t("wizard.submitRequest")}
        </button>
      </form>
    </div>
  );
}
