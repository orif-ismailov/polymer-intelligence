/**
 * Seller listing wizard (/sell/new) — IMG_0046 ③ / IMG_0043 bottom.
 *
 * Four stepped screens with a progress indicator (Основная информация → Количество
 * и цена → Фото и документы → Контакты и описание) → "Отправить на модерацию". On
 * submit it POSTs the offer, uploads staged photos, then shows the moderation
 * confirmation. Open self-serve: the seller is upserted from the contact + initData.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import StepIndicator from "../components/StepIndicator";
import FieldGroup from "../components/FieldGroup";
import SelectField from "../components/SelectField";
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
const CURRENCY = ["USD", "EUR", "UZS", "RUB"];
const INCOTERMS = ["unknown", "EXW", "FCA", "FOB", "CIF", "CPT", "DAP", "DDP"];
const UNITS = ["MT", "KG"];

const fieldStyle: CSSProperties = {
  display: "block",
  width: "100%",
  minHeight: "44px",
  padding: "10px 12px",
  borderRadius: "var(--r-md)",
  background: "var(--surface)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontSize: "14px",
  boxSizing: "border-box",
};

function primaryBtn(bg: string): CSSProperties {
  return {
    flex: 1,
    minHeight: "48px",
    padding: "12px 20px",
    borderRadius: "var(--r-md)",
    background: bg,
    color: "#ffffff",
    border: "none",
    fontSize: "16px",
    fontWeight: 600,
    cursor: "pointer",
  };
}

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
  const [incoterms, setIncoterms] = useState("unknown");
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

  const step1Valid = productId !== "" || productText.trim() !== "";
  const step2Valid = Number(qty) > 0 && Number(price) > 0;

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

  if (done) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "48px 16px", textAlign: "center" }}>
        <h1 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "8px" }}>{t("sellForm.success")}</h1>
        <p style={{ fontSize: "14px", color: "var(--text-muted)", marginBottom: "24px" }}>{t("sellForm.successBody")}</p>
        <button type="button" onClick={() => navigate("/sell")} style={{ ...primaryBtn("var(--green)"), color: "var(--green-on)" }}>
          {t("sellForm.backToOffers")}
        </button>
      </div>
    );
  }

  const canAdvance = step === 1 ? step1Valid : step === 2 ? step2Valid : true;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator current={step} total={4} />
      </div>

      <h1 style={{ margin: "0 0 20px", fontSize: "18px", fontWeight: 600 }}>{t(`sellForm.step${step}`)}</h1>

      {error && <p role="alert" style={{ color: "var(--danger)", fontSize: "14px", marginBottom: "8px" }}>{error}</p>}

      {step === 1 && (
        <>
          <FieldGroup htmlFor="s_product" label={t("wizard.product")}>
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
        </>
      )}

      {step === 2 && (
        <>
          <FieldGroup htmlFor="s_qty" label={`${t("sellForm.qtyAvailable")} *`}>
            <input id="s_qty" type="number" inputMode="decimal" min="0.01" step="any" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="100" style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_unit" label={t("wizard.volumeUnit")}>
            <SelectField id="s_unit" options={UNITS.map((u) => ({ value: u, label: t(`wizard.volumeUnit_${u}`, u) }))} value={qtyUnit} onChange={(e) => setQtyUnit(e.target.value)} />
          </FieldGroup>
          <FieldGroup htmlFor="s_price" label={`${t("sellForm.price")} *`}>
            <input id="s_price" type="number" inputMode="decimal" min="0.01" step="any" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="1200" style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_curr" label={t("wizard.currency")}>
            <SelectField id="s_curr" options={CURRENCY.map((c) => ({ value: c, label: c }))} value={currency} onChange={(e) => setCurrency(e.target.value)} />
          </FieldGroup>
          <FieldGroup htmlFor="s_inco" label={t("wizard.incoterms")}>
            <SelectField id="s_inco" options={INCOTERMS.map((i) => ({ value: i, label: i === "unknown" ? t("wizard.incotermsNone") : i }))} value={incoterms} onChange={(e) => setIncoterms(e.target.value)} />
          </FieldGroup>
          <FieldGroup htmlFor="s_city" label={t("sellForm.warehouseCity")}>
            <input id="s_city" type="text" value={warehouseCity} onChange={(e) => setWarehouseCity(e.target.value)} placeholder={t("wizard.portPlaceholder")} style={fieldStyle} />
          </FieldGroup>
          <FieldGroup htmlFor="s_min" label={t("sellForm.minOrder")}>
            <input id="s_min" type="number" inputMode="decimal" min="0" step="any" value={minOrder} onChange={(e) => setMinOrder(e.target.value)} placeholder="20" style={fieldStyle} />
          </FieldGroup>
        </>
      )}

      {step === 3 && (
        <FieldGroup htmlFor="s_photos" label={t("sellForm.photos")}>
          <input id="s_photos" type="file" accept="image/jpeg" multiple onChange={(e) => setPhotos(Array.from(e.target.files ?? []))} style={fieldStyle} />
          {photos.length > 0 && (
            <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
              {photos.length} {t("sellForm.photosCount")}
            </p>
          )}
        </FieldGroup>
      )}

      {step === 4 && (
        <>
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
          <button type="button" onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3 | 4)} style={{ ...primaryBtn("var(--surface)"), color: "var(--text)", border: "1px solid var(--border)" }}>
            {t("sellForm.back")}
          </button>
        )}
        {step < 4 ? (
          <button
            type="button"
            disabled={!canAdvance}
            onClick={() => canAdvance && setStep((s) => (s + 1) as 1 | 2 | 3 | 4)}
            style={{ ...primaryBtn(canAdvance ? "var(--orange)" : "var(--chip-neutral-bg)"), color: canAdvance ? "#ffffff" : "var(--text-muted)", cursor: canAdvance ? "pointer" : "not-allowed" }}
          >
            {t("wizard.next")}
          </button>
        ) : (
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submit()}
            style={{ ...primaryBtn("var(--orange)"), opacity: submitting ? 0.6 : 1 }}
          >
            {t("sellForm.submit")}
          </button>
        )}
      </div>
    </div>
  );
}
