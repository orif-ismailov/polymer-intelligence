/**
 * Запрос предложения — detail + edit for one of the buyer's own inquiries.
 *
 * Shows the targeted offer, the buyer's current terms, and the moderation status.
 * Pending/approved inquiries are editable; saving records the edit and (when anything
 * changed) re-enters review + notifies the seller of exactly what changed. Editing an
 * approved inquiry sends it back to `pending`. Rejected inquiries are read-only.
 *
 * BackButton → Мои запросы.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton, notifyError, notifySuccess } from "../telegram";
import FieldGroup from "../components/FieldGroup";
import Button from "../components/Button";
import type { OfferRequestOut } from "../types";

const FIELD_CLASS =
  "box-border block min-h-[48px] w-full rounded-[var(--r-md)] border border-border bg-surface p-3 text-base text-text disabled:opacity-60";

export default function InquiryDetail() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [inq, setInq] = useState<OfferRequestOut | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  const [qty, setQty] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/inquiries"));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setState("loading");
    api
      .getMyOfferRequest(Number(id))
      .then((data) => {
        if (cancelled) return;
        setInq(data);
        setQty(data.quantity != null ? String(data.quantity) : "");
        setTargetPrice(data.target_price != null ? String(data.target_price) : "");
        setMessage(data.message ?? "");
        setState("ok");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const editable = inq != null && inq.status !== "rejected";

  async function save() {
    if (!inq || submitting) return;
    if (!qty && !message.trim()) {
      setFormError(t("requestOffer.needQtyOrMessage"));
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const updated = await api.updateOfferRequest(inq.id, {
        quantity: qty ? Number(qty) : null,
        qty_unit: inq.qty_unit,
        target_price: targetPrice ? Number(targetPrice) : null,
        currency: inq.currency ?? inq.offer.currency,
        message: message.trim() || null,
      });
      setInq(updated);
      notifySuccess();
      setSaved(true);
    } catch {
      notifyError();
      setFormError(t("inquiries.saveError"));
    } finally {
      setSubmitting(false);
    }
  }

  if (state !== "ok" || !inq) {
    return (
      <div className="min-h-screen bg-bg px-4 py-8 text-center text-text-muted">
        {state === "error" ? t("offer.notFound") : "…"}
      </div>
    );
  }

  if (saved) {
    return (
      <div className="flex min-h-screen flex-col items-center bg-bg px-6 py-12 text-center text-text">
        <CheckCircle2 size={48} className="text-green" />
        <h1 className="mb-2 mt-4 text-xl font-bold">{t("inquiries.savedTitle")}</h1>
        <p className="mb-6 max-w-[320px] text-sm leading-relaxed text-text-muted">{t("inquiries.savedBody")}</p>
        <div className="w-full max-w-[360px]">
          <Button variant="primary" onClick={() => navigate("/inquiries")}>
            {t("inquiries.backToList")}
          </Button>
        </div>
      </div>
    );
  }

  const title = inq.offer.grade_text || inq.offer.product_text || "—";

  return (
    <div className="min-h-screen bg-bg p-4 text-text">
      <h1 className="mb-1 text-xl font-bold">{title}</h1>
      <p className="mb-4 text-[13px] text-text-muted">
        {inq.offer.price != null
          ? `${inq.offer.price.toLocaleString()} ${inq.offer.currency}/${inq.offer.qty_unit}`
          : t("offer.priceOnRequest")}{" "}
        · {t(`inquiries.status.${inq.status}`)}
      </p>

      {!editable && (
        <div className="mb-4 rounded-[var(--r-md)] border border-border bg-surface px-3.5 py-3 text-[13px] text-text-muted">
          {t("inquiries.rejectedNote")}
        </div>
      )}

      <FieldGroup htmlFor="i_qty" label={t("inquiries.qty")}>
        <input
          id="i_qty"
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          placeholder={inq.qty_unit}
          className={FIELD_CLASS}
          disabled={!editable}
        />
      </FieldGroup>
      <FieldGroup htmlFor="i_price" label={t("inquiries.targetPrice")}>
        <input
          id="i_price"
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={targetPrice}
          onChange={(e) => setTargetPrice(e.target.value)}
          placeholder={inq.currency ?? inq.offer.currency}
          className={FIELD_CLASS}
          disabled={!editable}
        />
      </FieldGroup>
      <FieldGroup htmlFor="i_msg" label={t("inquiries.message")}>
        <textarea
          id="i_msg"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={3}
          className={`${FIELD_CLASS} min-h-[80px] resize-y`}
          disabled={!editable}
        />
      </FieldGroup>

      {formError && (
        <p role="alert" className="mb-2 text-sm text-danger">
          {formError}
        </p>
      )}

      {editable && (
        <>
          {inq.status === "approved" && (
            <p className="mb-2.5 text-xs leading-snug text-text-muted">{t("inquiries.editApprovedHint")}</p>
          )}
          <Button variant="primary" disabled={submitting} onClick={() => void save()}>
            {t("inquiries.saveChanges")}
          </Button>
        </>
      )}
    </div>
  );
}
