/**
 * Offer detail (IMG_0043 ③) — full-screen public product card.
 *
 * Shows an approved catalog offer with a "Request an offer" inquiry form. The
 * seller's direct contact is NOT shown: buyer→seller contact is brokered through
 * admin review (a submitted inquiry is reviewed, then forwarded to the seller).
 * BackButton → Маркет.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BadgeCheck, CheckCircle2 } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import type { CatalogOffer } from "../types";

const rowLabel: CSSProperties = { fontSize: "13px", color: "var(--text-muted)" };
const rowValue: CSSProperties = { fontSize: "13px", color: "var(--text)", fontWeight: 600, textAlign: "right" };

export default function OfferDetail() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [offer, setOffer] = useState<CatalogOffer | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  // "Request an offer" inquiry form
  const [qty, setQty] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submitInquiry() {
    if (!offer || submitting) return;
    if (!qty && !message.trim()) {
      setFormError(t("requestOffer.needQtyOrMessage"));
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await api.requestOffer(offer.id, {
        quantity: qty ? Number(qty) : null,
        qty_unit: offer.qty_unit,
        target_price: targetPrice ? Number(targetPrice) : null,
        currency: offer.currency,
        message: message.trim() || null,
      });
      setSent(true);
    } catch {
      setFormError(t("requestOffer.error"));
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/market"));
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
      .getCatalogOffer(Number(id))
      .then((o) => {
        if (!cancelled) {
          setOffer(o);
          setState("ok");
        }
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (state !== "ok" || !offer) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text-muted)", padding: "32px 16px", textAlign: "center" }}>
        {state === "error" ? t("offer.notFound") : "…"}
      </div>
    );
  }

  const Row = ({ label, value }: { label: string; value: string }) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={rowLabel}>{label}</span>
      <span style={rowValue}>{value}</span>
    </div>
  );

  const images = offer.files?.filter((f) => f.kind === "image") ?? [];
  const docs = offer.files?.filter((f) => f.kind !== "image") ?? [];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <h1 style={{ margin: "0 0 4px", fontSize: "20px", fontWeight: 700 }}>
        {offer.grade_text || offer.product_text || "—"}
      </h1>
      {offer.polymer_type && (
        <p style={{ margin: "0 0 12px", fontSize: "13px", color: "var(--text-muted)" }}>{offer.polymer_type}</p>
      )}

      {images.length > 0 && (
        <div style={{ display: "flex", gap: "8px", overflowX: "auto", marginBottom: "16px" }}>
          {images.map((img) => (
            <img
              key={img.id}
              src={api.offerImageUrl(offer.id, img.id)}
              alt=""
              style={{ width: "200px", height: "150px", flex: "0 0 auto", borderRadius: "var(--r-md)", objectFit: "cover", background: "var(--surface-2)" }}
            />
          ))}
        </div>
      )}

      <div style={{ fontSize: "26px", fontWeight: 700, color: "var(--green)", marginBottom: "16px" }}>
        {offer.price.toLocaleString()} <span style={{ fontSize: "14px", color: "var(--text-muted)" }}>{offer.currency}/{offer.qty_unit}</span>
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-md)", padding: "4px 14px", marginBottom: "16px" }}>
        <Row label={t("offer.inStock")} value={`${offer.qty_available.toLocaleString()} ${offer.qty_unit}`} />
        {offer.min_order_qty != null && <Row label={t("offer.minOrder")} value={`${offer.min_order_qty.toLocaleString()} ${offer.qty_unit}`} />}
        <Row label={t("offer.supply")} value={String(offer.incoterms)} />
        {offer.warehouse_city && <Row label={t("offer.location")} value={offer.warehouse_city} />}
        <Row label={t("offer.seller")} value={offer.seller.company_name || "—"} />
      </div>

      {offer.description && (
        <p style={{ fontSize: "14px", color: "var(--text)", lineHeight: 1.5, marginBottom: "16px" }}>{offer.description}</p>
      )}

      {docs.length > 0 && (
        <div style={{ marginBottom: "16px", display: "flex", flexDirection: "column", gap: "6px" }}>
          {docs.map((d) => (
            <a
              key={d.id}
              href={api.offerImageUrl(offer.id, d.id)}
              target="_blank"
              rel="noreferrer"
              style={{ fontSize: "13px", color: "var(--blue)", textDecoration: "none" }}
            >
              📄 {d.file_name}
            </a>
          ))}
        </div>
      )}

      {offer.seller.is_verified && (
        <p style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "13px", color: "var(--green)", marginBottom: "12px" }}>
          <BadgeCheck size={16} /> {t("offer.verified")}
        </p>
      )}

      {sent ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "8px",
            textAlign: "center",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            padding: "20px 16px",
          }}
        >
          <CheckCircle2 size={40} color="var(--green)" />
          <h2 style={{ margin: 0, fontSize: "17px", fontWeight: 700 }}>{t("requestOffer.sentTitle")}</h2>
          <p style={{ margin: 0, fontSize: "14px", color: "var(--text-muted)", lineHeight: 1.5 }}>
            {t("requestOffer.sentBody")}
          </p>
          <button
            type="button"
            onClick={() => navigate("/market")}
            style={{ ...fullBtn("var(--green)", "var(--green-on)"), cursor: "pointer", marginTop: "8px" }}
          >
            {t("requestOffer.backToMarket")}
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <h2 style={{ margin: "4px 0 0", fontSize: "16px", fontWeight: 700 }}>{t("requestOffer.title")}</h2>
          <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted)", lineHeight: 1.4 }}>
            {t("requestOffer.hint")}
          </p>
          <input
            type="number"
            inputMode="decimal"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder={`${t("requestOffer.qty")} (${offer.qty_unit})`}
            style={inputStyle}
          />
          <input
            type="number"
            inputMode="decimal"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder={`${t("requestOffer.targetPrice")} (${offer.currency})`}
            style={inputStyle}
          />
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={t("requestOffer.messagePlaceholder")}
            rows={3}
            style={{ ...inputStyle, resize: "vertical" }}
          />
          {formError && <p style={{ margin: 0, fontSize: "13px", color: "var(--red, #e5484d)" }}>{formError}</p>}
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submitInquiry()}
            style={{ ...fullBtn("var(--green)", "var(--green-on)"), cursor: "pointer", opacity: submitting ? 0.6 : 1 }}
          >
            {t("offer.requestOffer")}
          </button>
        </div>
      )}
    </div>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  minHeight: "44px",
  padding: "10px 14px",
  borderRadius: "var(--r-md)",
  border: "1px solid var(--border)",
  background: "var(--surface)",
  color: "var(--text)",
  fontSize: "16px",
  boxSizing: "border-box",
};

function fullBtn(bg: string, fg: string, bordered = false): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    width: "100%",
    minHeight: "48px",
    padding: "12px 20px",
    borderRadius: "var(--r-md)",
    background: bg,
    color: fg,
    border: bordered ? "1px solid var(--border)" : "none",
    fontSize: "16px",
    fontWeight: 600,
    textDecoration: "none",
    boxSizing: "border-box",
  };
}
