/**
 * Seller listing wizard (/sell/new) — design_2 seller flow + IMG_0046 ③.
 *
 * Four stepped screens with a progress indicator:
 *   1 Основная информация  · 2 Количество и цена · 3 Фото и документы · 4 Проверка и публикация
 * Step 4 is a review summary + description/contact + publish; on submit it POSTs the
 * offer, uploads staged photos, then shows the moderation confirmation (Telegram glyph).
 * Open self-serve: the seller is upserted from the contact + initData.
 *
 * Reconciliation note: the publish CTA is ORANGE (documented seller-domain primary);
 * design_2 drew it green — see docs/design-system.md §Reconciliation.
 */

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ImagePlus, Send, X } from "lucide-react";

import StepIndicator from "../components/StepIndicator";
import FieldGroup from "../components/FieldGroup";
import SelectField from "../components/SelectField";
import Segmented from "../components/Segmented";
import Button from "../components/Button";
import { api } from "../api/client";
import { backButton, mainButton, notifySuccess, notifyError } from "../telegram";
import type { PriceBasis, SellerOfferCreate } from "../types";

const PRODUCTS = [
  { value: 1, label: "PP" },
  { value: 2, label: "HDPE" },
  { value: 3, label: "LDPE" },
  { value: 4, label: "LLDPE" },
  { value: 5, label: "PVC" },
  { value: 6, label: "PET" },
  { value: 7, label: "PS" },
  { value: 8, label: "ABS" },
];
const CURRENCY = ["USD", "UZS", "EUR", "RUB"];
const INCOTERMS = ["EXW", "FCA", "FOB", "CIF", "CPT", "DAP", "DDP"];
const UNITS = ["MT", "KG"];

const fieldStyle: CSSProperties = {
  display: "block",
  width: "100%",
  minHeight: "48px",
  padding: "12px",
  borderRadius: "var(--r-md)",
  background: "var(--surface)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontSize: "14px",
  boxSizing: "border-box",
};

const groupLabel: CSSProperties = {
  display: "block",
  margin: "0 0 6px",
  fontSize: "13px",
  fontWeight: 500,
  color: "var(--text-muted)",
};

export default function SellOffer() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  const [productId, setProductId] = useState("");
  const [productText, setProductText] = useState("");
  const [grade, setGrade] = useState("");
  const [polymerType, setPolymerType] = useState("");
  const [qty, setQty] = useState("");
  const [qtyUnit, setQtyUnit] = useState("MT");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [incoterms, setIncoterms] = useState("FCA");
  const [warehouseCity, setWarehouseCity] = useState("");
  const [minOrder, setMinOrder] = useState("");
  const [description, setDescription] = useState("");
  const [company, setCompany] = useState("");
  const [contact, setContact] = useState("");
  const [phone, setPhone] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const productLabel = productId ? PRODUCTS.find((p) => String(p.value) === productId)?.label : productText;
  const step1Valid = (productId !== "" || productText.trim() !== "") && warehouseCity.trim() !== "";
  const step2Valid = Number(qty) > 0 && Number(price) > 0;

  const thumbs = useMemo(() => photos.map((f) => URL.createObjectURL(f)), [photos]);
  useEffect(() => () => thumbs.forEach((u) => URL.revokeObjectURL(u)), [thumbs]);

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => {
      if (step > 1) setStep((s) => (s - 1) as 1 | 2 | 3 | 4);
      else navigate("/sell");
    });
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate, step]);

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    const body: SellerOfferCreate = {
      product_id: productId !== "" ? Number(productId) : null,
      product_text: productText.trim() || null,
      grade_text: grade.trim() || null,
      polymer_type: polymerType.trim() || null,
      qty_available: Number(qty),
      qty_unit: qtyUnit,
      price: Number(price),
      currency,
      incoterms: incoterms as PriceBasis,
      warehouse_city: warehouseCity.trim() || null,
      min_order_qty: minOrder ? Number(minOrder) : null,
      description: description.trim() || null,
      company_name: company.trim() || null,
      contact_name: contact.trim() || null,
      phone: phone.trim() || null,
    };
    try {
      const created = await api.createSellerOffer(body);
      for (const f of photos) {
        try {
          await api.uploadOfferFile(created.id, f, "image");
        } catch {
          /* keep the offer even if one image fails */
        }
      }
      notifySuccess();
      setDone(true);
    } catch {
      notifyError();
      setError(t("error.submitFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  // ── Moderation confirmation (design.jpeg seller ⑤ — Telegram glyph) ──────────
  if (done) {
    return (
      <div
        style={{
          minHeight: "100vh",
          background: "var(--bg)",
          color: "var(--text)",
          padding: "56px 24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
        }}
      >
        <span
          style={{
            width: "84px",
            height: "84px",
            borderRadius: "var(--r-full)",
            background: "var(--chip-warn-bg)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "24px",
          }}
        >
          <Send size={38} color="var(--blue)" />
        </span>
        <h1 style={{ fontSize: "22px", fontWeight: 700, margin: "0 0 12px" }}>{t("sellForm.success")}</h1>
        <p style={{ fontSize: "15px", lineHeight: 1.5, color: "var(--text-muted)", margin: "0 0 32px", maxWidth: "320px" }}>
          {t("sellForm.successBody")}
        </p>
        <div style={{ width: "100%", maxWidth: "360px", display: "flex", flexDirection: "column", gap: "10px" }}>
          <Button variant="seller" onClick={() => navigate("/sell")}>
            {t("sellForm.backToOffers")}
          </Button>
          <Button variant="secondary" onClick={() => navigate("/")}>
            {t("confirm.cta.home")}
          </Button>
        </div>
      </div>
    );
  }

  const canAdvance = step === 1 ? step1Valid : step === 2 ? step2Valid : true;

  const summaryRows: [string, string][] = [
    [t("wizard.product"), [productLabel, grade].filter(Boolean).join(" · ") || "—"],
    [t("sellForm.qtyAvailable"), qty ? `${Number(qty).toLocaleString()} ${qtyUnit}` : "—"],
    [t("sellForm.price"), price ? `${Number(price).toLocaleString()} ${currency}/${qtyUnit}` : "—"],
    [t("sellForm.warehouseCity"), warehouseCity || "—"],
    [t("wizard.incoterms"), incoterms],
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator
          current={step}
          total={4}
          accent="var(--orange)"
          subtitle={t("wizard.stepOf", { current: step, total: 4 })}
        />
      </div>

      <h1 style={{ margin: "0 0 20px", fontSize: "17px", fontWeight: 600 }}>{t(`sellForm.step${step}`)}</h1>

      {error && <p role="alert" style={{ color: "var(--danger)", fontSize: "14px", marginBottom: "8px" }}>{error}</p>}

      {step === 1 && (
        <>
          <FieldGroup htmlFor="s_product" label={t("wizard.product")} required>
            <SelectField id="s_product" options={PRODUCTS} placeholder={t("wizard.productPlaceholder")} value={productId} onChange={(e) => setProductId(e.target.value)} />
          </FieldGroup>
          <FieldGroup htmlFor="s_ptext" label={t("wizard.productText")}>
            <input id="s_ptext" type="text" value={productText} onChange={(e) => setProductText(e.target.value)} placeholder={t("wizard.productTextPlaceholder")} style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_grade" label={t("wizard.grade")}>
            <input id="s_grade" type="text" value={grade} onChange={(e) => setGrade(e.target.value)} placeholder={t("wizard.gradePlaceholder")} style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_ptype" label={t("wizard.polymerType")}>
            <input id="s_ptype" type="text" value={polymerType} onChange={(e) => setPolymerType(e.target.value)} placeholder={t("wizard.polymerTypePlaceholder")} style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_city" label={t("sellForm.warehouseCity")} required>
            <input id="s_city" type="text" value={warehouseCity} onChange={(e) => setWarehouseCity(e.target.value)} placeholder={t("wizard.portPlaceholder")} style={fieldStyle} />
          </FieldGroup>
        </>
      )}

      {step === 2 && (
        <>
          <FieldGroup htmlFor="s_qty" label={t("sellForm.qtyAvailable")} required>
            <input id="s_qty" type="number" inputMode="decimal" min="0.01" step="any" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="100" style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_unit" label={t("wizard.volumeUnit")}>
            <SelectField id="s_unit" options={UNITS.map((u) => ({ value: u, label: t(`wizard.volumeUnit_${u}`, u) }))} value={qtyUnit} onChange={(e) => setQtyUnit(e.target.value)} />
          </FieldGroup>
          <FieldGroup htmlFor="s_min" label={t("sellForm.minOrder")}>
            <input id="s_min" type="number" inputMode="decimal" min="0" step="any" value={minOrder} onChange={(e) => setMinOrder(e.target.value)} placeholder="20" style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_price" label={t("sellForm.price")} required>
            <input id="s_price" type="number" inputMode="decimal" min="0.01" step="any" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="1200" style={fieldStyle} />
          </FieldGroup>
          <div style={{ marginBottom: "16px" }}>
            <span style={groupLabel}>{t("wizard.currency")}</span>
            <Segmented<string> value={currency} options={CURRENCY.map((c) => ({ value: c, label: c }))} onChange={setCurrency} ariaLabel={t("wizard.currency")} />
          </div>
          <div style={{ marginBottom: "16px" }}>
            <span style={groupLabel}>{t("wizard.incoterms")}</span>
            <Segmented<string> value={incoterms} options={INCOTERMS.map((i) => ({ value: i, label: i }))} onChange={setIncoterms} ariaLabel={t("wizard.incoterms")} />
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <span style={groupLabel}>{t("sellForm.photos")}</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "16px" }}>
            {photos.map((f, i) => (
              <span key={`${f.name}-${i}`} style={{ position: "relative", width: "84px", height: "84px" }}>
                <img src={thumbs[i]} alt="" style={{ width: "84px", height: "84px", objectFit: "cover", borderRadius: "var(--r-sm)", border: "1px solid var(--border)" }} />
                <button
                  type="button"
                  aria-label={t("fileUploader.remove", { name: f.name })}
                  onClick={() => setPhotos(photos.filter((_, j) => j !== i))}
                  style={{ position: "absolute", top: "-6px", right: "-6px", width: "22px", height: "22px", borderRadius: "var(--r-full)", background: "var(--danger)", color: "#ffffff", border: "none", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
            <label
              htmlFor="s_photos"
              style={{
                width: "84px",
                height: "84px",
                borderRadius: "var(--r-sm)",
                border: "1.5px dashed var(--border)",
                background: "var(--surface)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: "4px",
                cursor: "pointer",
                color: "var(--text-muted)",
                fontSize: "11px",
                fontWeight: 600,
                textAlign: "center",
              }}
            >
              <ImagePlus size={20} />
              {t("sellForm.addPhoto")}
              <input
                id="s_photos"
                type="file"
                accept="image/jpeg"
                multiple
                onChange={(e) => setPhotos([...photos, ...Array.from(e.target.files ?? [])])}
                style={{ display: "none" }}
              />
            </label>
          </div>
          <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>{t("sellForm.docsHint")}</p>
        </>
      )}

      {step === 4 && (
        <>
          <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "4px 14px", marginBottom: "20px" }}>
            {summaryRows.map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "10px 0", borderBottom: "1px solid var(--border)", fontSize: "13px" }}>
                <span style={{ color: "var(--text-muted)" }}>{k}</span>
                <span style={{ color: "var(--text)", fontWeight: 600, textAlign: "right" }}>{v}</span>
              </div>
            ))}
          </div>
          <FieldGroup htmlFor="s_desc" label={t("sellForm.description")}>
            <textarea id="s_desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} style={{ ...fieldStyle, minHeight: "80px", resize: "vertical" }} />
          </FieldGroup>
          <FieldGroup htmlFor="s_company" label={t("wizard.companyName")}>
            <input id="s_company" type="text" value={company} onChange={(e) => setCompany(e.target.value)} placeholder={t("wizard.companyPlaceholder")} style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_contact" label={t("wizard.contactName")}>
            <input id="s_contact" type="text" value={contact} onChange={(e) => setContact(e.target.value)} placeholder={t("wizard.contactPlaceholder")} style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_phone" label={t("wizard.phone")}>
            <input id="s_phone" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+998 __ ___ __ __" style={fieldStyle} />
          </FieldGroup>
        </>
      )}

      <div style={{ display: "flex", gap: "8px", marginTop: "20px" }}>
        {step > 1 && (
          <Button variant="secondary" style={{ flex: 1 }} onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3 | 4)}>
            {t("sellForm.back")}
          </Button>
        )}
        {step < 4 ? (
          <Button variant="seller" style={{ flex: 1 }} disabled={!canAdvance} onClick={() => canAdvance && setStep((s) => (s + 1) as 1 | 2 | 3 | 4)}>
            {t("wizard.next")}
          </Button>
        ) : (
          <Button variant="seller" style={{ flex: 1, opacity: submitting ? 0.6 : 1 }} disabled={submitting} onClick={() => void submit()}>
            {t("sellForm.publish")}
          </Button>
        )}
      </div>
    </div>
  );
}
