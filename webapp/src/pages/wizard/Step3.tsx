/**
 * C-04 — Step 3: Additional information + file attachment.
 *
 * MainButton label changes to "Отправить" on this step.
 * BackButton → Step 2 (state preserved).
 * Submit triggers Confirm.tsx (via navigate to /request/confirm with state).
 * Focus moves to step heading on mount (accessibility).
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import StepIndicator from "../../components/StepIndicator";
import FieldGroup from "../../components/FieldGroup";
import FileUploader from "../../components/FileUploader";
import { mainButton, backButton } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";

const fieldStyle = {
  display: "block",
  width: "100%",
  padding: "10px 12px",
  borderRadius: "8px",
  backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
  color: "var(--tg-theme-text-color, #f8fafc)",
  border: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
  fontSize: "14px",
  fontFamily: "system-ui, sans-serif",
  boxSizing: "border-box" as const,
  resize: "vertical" as const,
  minHeight: "100px",
};

export default function Step3() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const store = useWizardStore();
  const [comment, setComment] = useState(store.comment);

  // Focus heading on mount
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // BackButton → Step 2 (save comment)
  useEffect(() => {
    backButton.show();
    const cleanupBack = backButton.onClick(() => {
      store.setField("comment", comment);
      navigate("/request/step/2");
    });
    return () => { cleanupBack(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, comment]);

  // MainButton shows "Отправить" on step 3
  useEffect(() => {
    mainButton.setText(t("wizard.submit"));
    mainButton.show();
    mainButton.enable();
  }, [t]);

  // MainButton click → save comment + navigate to confirm
  useEffect(() => {
    const cleanupMain = mainButton.onClick(() => {
      store.setField("comment", comment);
      navigate("/request/confirm");
    });
    return () => { cleanupMain(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, comment]);

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
        <StepIndicator current={3} total={4} />
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
        {t("wizard.step3.title")}
      </h2>

      <form onSubmit={(e) => e.preventDefault()}>
        {/* Comment */}
        <FieldGroup htmlFor="comment" label={t("wizard.comment")}>
          <textarea
            id="comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={t("wizard.commentPlaceholder")}
            rows={4}
            style={fieldStyle}
          />
        </FieldGroup>

        {/* File attachment */}
        <FieldGroup htmlFor="file-uploader-input" label={t("fileUploader.attach")}>
          <FileUploader />
        </FieldGroup>

        {/* Fallback button for non-Telegram (dev) */}
        <button
          type="button"
          onClick={() => {
            store.setField("comment", comment);
            navigate("/request/confirm");
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
          {t("wizard.submit")}
        </button>
      </form>
    </div>
  );
}
