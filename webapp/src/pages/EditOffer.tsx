/**
 * Редактировать предложение (/sell/:id/edit) — the seller edits their own listing.
 *
 * A single-screen form pre-filled from the offer. Saving replaces the offer's fields;
 * if the listing was already public (approved) — or previously rejected — it re-enters
 * moderation before the change appears in the catalog again (the backend owns that
 * transition; this screen just surfaces the hint). Owner-only: a foreign/absent id 404s.
 *
 * BackButton → Продать. Built with Tailwind (design tokens via utility classes).
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CheckCircle2 } from "lucide-react";

import FieldGroup from "../components/FieldGroup";
import SelectField from "../components/SelectField";
import Segmented from "../components/Segmented";
import IncotermsField from "../components/IncotermsField";
import Button from "../components/Button";
import { api } from "../api/client";
import { backButton, mainButton, notifyError, notifySuccess } from "../telegram";
import { useProducts } from "../hooks/useProducts";
import { availabilityRequiresLocation } from "../util/offer";
import type { OfferAvailability, PriceBasis, SellerOfferOut, SellerOfferUpdate } from "../types";

const CURRENCY = ["USD", "UZS", "EUR", "RUB"];
const UNITS = ["MT", "KG"];

const FIELD_CLASS =
  "box-border block min-h-[48px] w-full rounded-[var(--r-md)] border border-border bg-surface p-3 text-base text-text";

export default function EditOffer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { products } = useProducts();

  const [offer, setOffer] = useState<SellerOfferOut | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  const [productId, setProductId] = useState("");
  const [productText, setProductText] = useState("");
  const [grade, setGrade] = useState("");
  const [polymerType, setPolymerType] = useState("");
  const [availability, setAvailability] = useState<OfferAvailability>("in_stock");
  const [qty, setQty] = useState("");
  const [qtyUnit, setQtyUnit] = useState("MT");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [incoterms, setIncoterms] = useState("FCA");
  const [warehouseCity, setWarehouseCity] = useState("");
  const [minOrder, setMinOrder] = useState("");
  const [description, setDescription] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/sell"));
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
      .getMyOffer(Number(id))
      .then((o) => {
        if (cancelled) return;
        setOffer(o);
        setProductId(o.product_id != null ? String(o.product_id) : o.product_text ? "other" : "");
        setProductText(o.product_text ?? "");
        setGrade(o.grade_text ?? "");
        setPolymerType(o.polymer_type ?? "");
        setAvailability(o.availability);
        setQty(o.qty_available != null ? String(o.qty_available) : "");
        setQtyUnit(o.qty_unit);
        setPrice(o.price != null ? String(o.price) : "");
        setCurrency(o.currency);
        setIncoterms(String(o.incoterms) === "unknown" ? "FCA" : String(o.incoterms));
        setWarehouseCity(o.warehouse_city ?? "");
        setMinOrder(o.min_order_qty != null ? String(o.min_order_qty) : "");
        setDescription(o.description ?? "");
        setState("ok");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const isOtherProduct = productId === "other";
  // «Под заказ» (on_order) goods have no warehouse — hide the location field and drop it from the payload.
  const requiresLocation = availabilityRequiresLocation(availability);
  const valid =
    (isOtherProduct ? productText.trim() !== "" : productId !== "") &&
    Number(qty) > 0 &&
    Number(price) > 0;

  async function save() {
    if (!offer || submitting) return;
    setSubmitting(true);
    setFormError(null);
    const body: SellerOfferUpdate = {
      product_id: productId !== "" && !isOtherProduct ? Number(productId) : null,
      product_text: isOtherProduct ? productText.trim() || null : null,
      grade_text: grade.trim() || null,
      polymer_type: polymerType.trim() || null,
      availability,
      qty_available: Number(qty),
      qty_unit: qtyUnit,
      price: Number(price),
      currency,
      incoterms: incoterms as PriceBasis,
      warehouse_city: requiresLocation ? warehouseCity.trim() || null : null,
      min_order_qty: minOrder ? Number(minOrder) : null,
      description: description.trim() || null,
    };
    try {
      await api.updateSellerOffer(offer.id, body);
      notifySuccess();
      setSaved(true);
    } catch {
      notifyError();
      setFormError(t("editOffer.saveError"));
    } finally {
      setSubmitting(false);
    }
  }

  if (state !== "ok" || !offer) {
    return (
      <div className="min-h-screen bg-bg px-4 py-8 text-center text-text-muted">
        {state === "error" ? t("editOffer.loadError") : "…"}
      </div>
    );
  }

  if (saved) {
    return (
      <div className="flex min-h-screen flex-col items-center bg-bg px-6 py-12 text-center text-text">
        <CheckCircle2 size={48} className="text-green" />
        <h1 className="mb-2 mt-4 text-xl font-bold">{t("editOffer.savedTitle")}</h1>
        <p className="mb-6 max-w-[320px] text-sm leading-relaxed text-text-muted">
          {t("editOffer.savedBody")}
        </p>
        <div className="w-full max-w-[360px]">
          <Button variant="seller" onClick={() => navigate("/sell")}>
            {t("editOffer.backToOffers")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg p-4 text-text">
      <h1 className="mb-4 text-lg font-semibold">{t("editOffer.title")}</h1>

      {(offer.status === "approved" || offer.status === "rejected") && (
        <p className="mb-4 rounded-[var(--r-md)] border border-border bg-surface px-3.5 py-3 text-xs leading-snug text-text-muted">
          {t("editOffer.moderationHint")}
        </p>
      )}

      <FieldGroup htmlFor="e_product" label={t("wizard.product")} required>
        <SelectField
          id="e_product"
          options={[
            ...products.map((p) => ({ value: p.id, label: p.code })),
            { value: "other", label: t("wizard.productOther") },
          ]}
          placeholder={t("wizard.productPlaceholder")}
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
        />
      </FieldGroup>
      {isOtherProduct && (
        <FieldGroup htmlFor="e_ptext" label={t("wizard.productManual")} required>
          <input
            id="e_ptext"
            type="text"
            value={productText}
            onChange={(e) => setProductText(e.target.value)}
            placeholder={t("wizard.productTextPlaceholder")}
            className={FIELD_CLASS}
          />
        </FieldGroup>
      )}
      <FieldGroup htmlFor="e_grade" label={t("wizard.grade")}>
        <input
          id="e_grade"
          type="text"
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
          placeholder={t("wizard.gradePlaceholder")}
          className={FIELD_CLASS}
        />
      </FieldGroup>
      <FieldGroup htmlFor="e_ptype" label={t("wizard.polymerType")}>
        <input
          id="e_ptype"
          type="text"
          value={polymerType}
          onChange={(e) => setPolymerType(e.target.value)}
          placeholder={t("wizard.polymerTypePlaceholder")}
          className={FIELD_CLASS}
        />
      </FieldGroup>

      <div className="mb-4">
        <span className="mb-1.5 block text-[13px] font-medium text-text-muted">{t("availability.label")}</span>
        <Segmented<OfferAvailability>
          value={availability}
          options={[
            { value: "in_stock", label: t("availability.in_stock") },
            { value: "on_order", label: t("availability.on_order") },
          ]}
          onChange={setAvailability}
          ariaLabel={t("availability.label")}
        />
      </div>

      <FieldGroup htmlFor="e_qty" label={t("sellForm.qtyAvailable")} required>
        <input
          id="e_qty"
          type="number"
          inputMode="decimal"
          min="0.01"
          step="any"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          placeholder="100"
          className={FIELD_CLASS}
        />
      </FieldGroup>
      <FieldGroup htmlFor="e_unit" label={t("wizard.volumeUnit")}>
        <SelectField
          id="e_unit"
          options={UNITS.map((u) => ({ value: u, label: t(`wizard.volumeUnit_${u}`, u) }))}
          value={qtyUnit}
          onChange={(e) => setQtyUnit(e.target.value)}
        />
      </FieldGroup>
      <FieldGroup htmlFor="e_min" label={t("sellForm.minOrder")}>
        <input
          id="e_min"
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={minOrder}
          onChange={(e) => setMinOrder(e.target.value)}
          placeholder="20"
          className={FIELD_CLASS}
        />
      </FieldGroup>
      <FieldGroup htmlFor="e_price" label={t("sellForm.price")} required>
        <input
          id="e_price"
          type="number"
          inputMode="decimal"
          min="0.01"
          step="any"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="1200"
          className={FIELD_CLASS}
        />
      </FieldGroup>

      <div className="mb-4">
        <span className="mb-1.5 block text-[13px] font-medium text-text-muted">{t("wizard.currency")}</span>
        <Segmented<string>
          value={currency}
          options={CURRENCY.map((c) => ({ value: c, label: c }))}
          onChange={setCurrency}
          ariaLabel={t("wizard.currency")}
        />
      </div>
      <IncotermsField value={incoterms} onChange={setIncoterms} />

      {requiresLocation ? (
        <FieldGroup htmlFor="e_city" label={t("sellForm.warehouseCity")}>
          <input
            id="e_city"
            type="text"
            value={warehouseCity}
            onChange={(e) => setWarehouseCity(e.target.value)}
            placeholder={t("wizard.portPlaceholder")}
            className={FIELD_CLASS}
          />
        </FieldGroup>
      ) : (
        <p className="mb-4 text-xs leading-relaxed text-text-muted">
          {t("sellForm.warehouseCityByOrderHint")}
        </p>
      )}
      <FieldGroup htmlFor="e_desc" label={t("sellForm.description")}>
        <textarea
          id="e_desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className={`${FIELD_CLASS} min-h-[80px] resize-y`}
        />
      </FieldGroup>

      {formError && (
        <p role="alert" className="mb-2 text-sm text-danger">
          {formError}
        </p>
      )}

      <Button variant="seller" disabled={!valid || submitting} onClick={() => void save()}>
        {t("editOffer.save")}
      </Button>
    </div>
  );
}
