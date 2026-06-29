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
import { Check, Sparkles } from "lucide-react";

import Button from "../../components/Button";
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
          background: "var(--bg)",
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
            border: "3px solid var(--border)",
            borderTopColor: "var(--green)",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <p style={{ fontSize: "14px", color: "var(--text-muted)", margin: 0 }}>{t("confirm.subheading")}</p>
      </div>
    );
  }

  if (submitState === "error") {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", padding: "16px" }}>
        {/* Error banner */}
        <div
          role="alert"
          style={{
            padding: "12px 16px",
            borderRadius: "var(--r-md)",
            backgroundColor: "var(--chip-down-bg)",
            color: "var(--chip-down-fg)",
            fontSize: "14px",
            marginBottom: "16px",
          }}
        >
          {errorMsg}
        </div>

        {/* Retry button */}
        <Button variant="primary" onClick={() => void doSubmit()}>
          {t("wizard.submitRequest")}
        </Button>
      </div>
    );
  }

  // Success (submitState === "success")
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "56px 24px 32px",
      }}
    >
      {/* Green check in ring, with a subtle AI glow (design "Заявка принята!") */}
      <div
        style={{
          position: "relative",
          width: "104px",
          height: "104px",
          marginBottom: "28px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "var(--r-full)",
            background: "var(--chip-ok-bg)",
          }}
        />
        <span
          style={{
            position: "relative",
            width: "72px",
            height: "72px",
            borderRadius: "var(--r-full)",
            background: "var(--green)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 8px 24px rgba(34,197,94,.35)",
          }}
        >
          <Check size={38} color="var(--green-on)" strokeWidth={3} />
        </span>
        <Sparkles
          size={20}
          color="var(--green)"
          style={{ position: "absolute", top: "2px", right: "6px" }}
          aria-hidden="true"
        />
      </div>

      <h1 style={{ margin: "0 0 12px", fontSize: "22px", fontWeight: 700, textAlign: "center" }}>
        {t("confirm.heading")}
      </h1>

      {/* AI-tender note (design "Заявка принята") */}
      <p
        style={{
          margin: "0 0 20px",
          fontSize: "14px",
          color: "var(--text-muted)",
          textAlign: "center",
          lineHeight: 1.5,
          maxWidth: "320px",
        }}
      >
        {t("confirm.aiNote")}
      </p>

      {/* REQ number + status chip */}
      <p style={{ margin: "0 0 10px", fontSize: "15px", fontWeight: 600, color: "var(--text)" }}>{reqNumber}</p>
      <div style={{ marginBottom: "32px" }}>
        <StatusChip status="new" />
      </div>

      {/* CTAs */}
      <div style={{ width: "100%", maxWidth: "360px", display: "flex", flexDirection: "column", gap: "10px" }}>
        <Button variant="primary" onClick={() => navigate("/requests")}>
          {t("confirm.cta.myRequests")}
        </Button>
        <Button variant="secondary" onClick={() => navigate("/")}>
          {t("confirm.cta.home")}
        </Button>
        <button
          type="button"
          onClick={handleAnother}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-muted)",
            fontSize: "14px",
            fontWeight: 600,
            cursor: "pointer",
            padding: "8px",
          }}
        >
          {t("confirm.cta.another")}
        </button>
      </div>
    </div>
  );
}
