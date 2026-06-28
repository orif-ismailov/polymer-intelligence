/**
 * C-05 — Confirmation screen.
 *
 * Triggered when Step3 MainButton fires (navigate to /request/confirm).
 * On mount: build RequestCreate from store, POST /webapp/requests, then
 * sequentially upload each staged file (for-await loop, NOT Promise.all — D-01).
 *
 * Success:
 *   - notifySuccess() haptic
 *   - shows REQ number + StatusChip "Новая заявка"
 *   - CTA 1: Мои заявки → /requests
 *   - CTA 2: Создать ещё одну → reset store + /request/step/1
 *
 * Error:
 *   - shows ErrorBanner with t('error.submitFailed') or t('error.fileFailed', {name})
 *   - re-enables MainButton / fallback button
 *
 * BackButton is hidden on C-05.
 * MainButton is hidden on C-05 (after submission completes or errors).
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import StatusChip from "../../components/StatusChip";
import { mainButton, backButton, notifySuccess, notifyError } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";
import { api } from "../../api/client";
import type { RequestCreate } from "../../types";

type SubmitState = "submitting" | "success" | "error";

export default function Confirm() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const store = useWizardStore();

  const [submitState, setSubmitState] = useState<SubmitState>("submitting");
  const [reqNumber, setReqNumber] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Hide BackButton and MainButton on this screen
  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  const doSubmit = useCallback(async () => {
    setSubmitState("submitting");

    // Fold the availability preference (IMG_0044 radio cards) into the comment so
    // the sales team sees it — it has no dedicated column.
    const availLabels: Record<string, string> = {
      tashkent: "В наличии в Ташкенте",
      uzbekistan: "В Узбекистане",
      import: "Импорт",
      any: "",
    };
    const availLine = availLabels[store.availability]
      ? `Наличие: ${availLabels[store.availability]}`
      : "";
    const fullComment = [availLine, store.comment].filter(Boolean).join("\n") || null;

    // Build RequestCreate from wizard store
    const body: RequestCreate = {
      product_id: store.product_id ?? null,
      product_text: store.product_text || null,
      grade_text: store.grade_text || null,
      polymer_type: store.polymer_type || null,
      volume: Number(store.volume),
      volume_unit: store.volume_unit,
      target_price: store.target_price ? Number(store.target_price) : null,
      currency: store.currency,
      incoterms: store.incoterms as RequestCreate["incoterms"],
      destination_country: store.destination_country,
      port_or_city: store.port_or_city || null,
      desired_date: store.desired_date || null,
      validity_days: Number(store.validity_days) || 30,
      urgency: store.urgency as RequestCreate["urgency"],
      comment: fullComment,
      company_name: store.company_name || null,
      contact_name: store.contact_name || null,
      phone: store.phone || null,
      legal_address: store.legal_address || null,
    };

    try {
      // POST /webapp/requests
      const req = await api.createRequest(body);

      // Sequential file uploads (for-await loop, NOT Promise.all — D-01)
      for (const file of store.files) {
        try {
          await api.uploadFile(req.id, file);
        } catch {
          // File upload failure — show error but still mark request as created
          setErrorMsg(t("error.fileFailed", { name: file.name }));
          setSubmitState("error");
          notifyError();
          return;
        }
      }

      // Success
      setReqNumber(req.number);
      setSubmitState("success");
      notifySuccess();
    } catch {
      setErrorMsg(t("error.submitFailed"));
      setSubmitState("error");
      notifyError();
    }
  }, [store, t]);

  // Submit on mount — exactly once. The ref guard makes this idempotent under React
  // StrictMode's double-invoked mount effect (dev) and any remount, so we never POST
  // the request twice (which created a duplicate AND raced the backend into a 500).
  // The Retry button below calls doSubmit() directly and is intentionally not gated.
  const autoSubmittedRef = useRef(false);
  useEffect(() => {
    if (autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    void doSubmit();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleAnother() {
    store.reset();
    navigate("/request/step/1");
  }

  if (submitState === "submitting") {
    return (
      <div
        style={{
          minHeight: "100vh",
          backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "32px 16px",
          gap: "16px",
        }}
      >
        {/* Loading spinner */}
        <div
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "50%",
            border: "3px solid var(--tg-theme-secondary-bg-color, #334155)",
            borderTopColor: "var(--tg-theme-button-color, #10b981)",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <p
          style={{
            fontSize: "14px",
            color: "var(--tg-theme-hint-color, #94a3b8)",
            margin: 0,
          }}
        >
          {t("confirm.subheading")}
        </p>
      </div>
    );
  }

  if (submitState === "error") {
    return (
      <div
        style={{
          minHeight: "100vh",
          backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
          padding: "16px",
        }}
      >
        {/* Error banner */}
        <div
          role="alert"
          style={{
            padding: "12px 16px",
            borderRadius: "8px",
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            color: "#ef4444",
            fontSize: "14px",
            marginBottom: "16px",
          }}
        >
          {errorMsg}
        </div>

        {/* Retry button */}
        <button
          type="button"
          onClick={() => void doSubmit()}
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
          }}
        >
          {t("wizard.submit")}
        </button>
      </div>
    );
  }

  // Success (submitState === "success")
  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "48px 16px 32px",
      }}
    >
      {/* Success check icon — accent fill */}
      <CheckCircle2
        size={64}
        color="var(--tg-theme-button-color, #10b981)"
        aria-hidden="true"
        style={{ marginBottom: "24px" }}
      />

      <h1
        style={{
          margin: "0 0 8px",
          fontSize: "18px",
          fontWeight: 600,
          color: "var(--tg-theme-text-color, #f8fafc)",
          textAlign: "center",
        }}
      >
        {t("confirm.heading")}
      </h1>

      <p
        style={{
          margin: "0 0 16px",
          fontSize: "14px",
          color: "var(--tg-theme-hint-color, #94a3b8)",
          textAlign: "center",
        }}
      >
        {t("confirm.subheading")}
      </p>

      {/* REQ number — 15px/600 per UI-SPEC §Typography */}
      <p
        style={{
          margin: "0 0 12px",
          fontSize: "15px",
          fontWeight: 600,
          color: "var(--tg-theme-text-color, #f8fafc)",
        }}
      >
        {reqNumber}
      </p>

      {/* Status chip — "Новая заявка" */}
      <div style={{ marginBottom: "32px" }}>
        <StatusChip status="new" />
      </div>

      {/* CTAs */}
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: "8px" }}>
        <button
          type="button"
          onClick={() => navigate("/requests")}
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
          }}
        >
          {t("confirm.cta.myRequests")}
        </button>

        <button
          type="button"
          onClick={handleAnother}
          style={{
            display: "block",
            width: "100%",
            minHeight: "44px",
            padding: "12px 20px",
            borderRadius: "8px",
            backgroundColor: "transparent",
            color: "var(--tg-theme-link-color, #38bdf8)",
            border: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
            fontSize: "14px",
            fontWeight: 400,
            cursor: "pointer",
            boxSizing: "border-box",
          }}
        >
          {t("confirm.cta.another")}
        </button>
      </div>
    </div>
  );
}
