/**
 * C-02 — Step 1: Product information (of 4).
 *
 * Minimum-to-submit: (product_id selected OR product_text typed) + volume > 0 +
 * (grade_text OR polymer_type). The buyer may type a product that is not in our
 * catalog (product_text) — IMG_0046 "не нашли? введите вручную".
 *
 * Product list: static localized constant matching seeded polymers. IDs 1–8 match
 * seed_reference.py order.
 */

import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import StepIndicator from "../../components/StepIndicator";
import FieldGroup from "../../components/FieldGroup";
import SelectField from "../../components/SelectField";
import HintBanner from "../../components/HintBanner";
import { mainButton, backButton, impactLight } from "../../telegram";
import { useWizardStore } from "../../store/wizardStore";
import { useProducts, productName } from "../../hooks/useProducts";

const VOLUME_UNIT_VALUES = ["MT", "KG"] as const;

const step1Schema = z
  .object({
    product_id: z.string().optional(),
    product_text: z.string().optional(),
    grade_text: z.string().optional(),
    polymer_type: z.string().optional(),
    volume: z.coerce
      .number({ invalid_type_error: "volumePositive" })
      .positive({ message: "volumePositive" }),
    volume_unit: z.string().min(1),
  })
  .refine(
    (d) => {
      // "Другое" (other) requires the manual product name; any real product is enough.
      if (d.product_id === "other") return d.product_text != null && d.product_text.trim() !== "";
      return d.product_id != null && d.product_id !== "";
    },
    { message: "productRequired", path: ["product_id"] },
  )
  .refine(
    (d) => {
      const gradeOk = d.grade_text != null && d.grade_text.trim() !== "";
      const polymerOk = d.polymer_type != null && d.polymer_type.trim() !== "";
      return gradeOk || polymerOk;
    },
    { message: "gradeOrPolymer", path: ["grade_text"] },
  );

type Step1Fields = z.infer<typeof step1Schema>;

const fieldStyle = {
  display: "block",
  width: "100%",
  minHeight: "44px",
  padding: "10px 12px",
  borderRadius: "var(--r-md)",
  backgroundColor: "var(--surface)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontSize: "16px",
  boxSizing: "border-box" as const,
};

function persist(store: ReturnType<typeof useWizardStore.getState>, data: Step1Fields) {
  const isOther = data.product_id === "other";
  const pid = !isOther && data.product_id && data.product_id !== "" ? Number(data.product_id) : null;
  store.setField("product_id", pid);
  store.setField("product_text", isOther ? data.product_text?.trim() ?? "" : "");
  store.setField("grade_text", data.grade_text ?? "");
  store.setField("polymer_type", data.polymer_type ?? "");
  store.setField("volume", String(data.volume));
  store.setField("volume_unit", data.volume_unit);
}

export default function Step1() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const store = useWizardStore();

  const { products } = useProducts();

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isValid },
  } = useForm<Step1Fields>({
    resolver: zodResolver(step1Schema),
    mode: "onChange",
    defaultValues: {
      product_id: store.product_id != null ? String(store.product_id) : store.product_text ? "other" : "",
      product_text: store.product_text,
      grade_text: store.grade_text,
      polymer_type: store.polymer_type,
      volume: store.volume ? Number(store.volume) : undefined,
      volume_unit: store.volume_unit,
    },
  });

  const formValues = watch();

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    backButton.show();
    const cleanupBack = backButton.onClick(() => navigate("/requests"));
    return () => {
      cleanupBack();
    };
  }, [navigate]);

  useEffect(() => {
    mainButton.setText(t("wizard.next"));
    mainButton.show();
    if (isValid) {
      mainButton.enable();
    } else {
      mainButton.disable();
    }
  }, [isValid, t, formValues]);

  useEffect(() => {
    const cleanupMain = mainButton.onClick(() => {
      void handleSubmit((data) => {
        persist(store, data);
        impactLight();
        navigate("/request/step/2");
      })();
    });
    return () => {
      cleanupMain();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate]);

  const productError = errors.product_id?.message
    ? t(`error.${errors.product_id.message}`, errors.product_id.message)
    : undefined;
  const gradeError = errors.grade_text?.message
    ? t(`error.${errors.grade_text.message}`, errors.grade_text.message)
    : undefined;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ marginBottom: "24px" }}>
        <StepIndicator current={1} total={4} subtitle={t("wizard.stepOf", { current: 1, total: 4 })} />
      </div>

      <h2
        ref={headingRef}
        tabIndex={-1}
        style={{ margin: "0 0 16px", fontSize: "17px", fontWeight: 600, color: "var(--text)", outline: "none" }}
      >
        {t("wizard.step1.title")}
      </h2>

      <HintBanner>{t("wizard.hintGrade")}</HintBanner>

      <form onSubmit={(e) => e.preventDefault()}>
        <FieldGroup htmlFor="product_id" label={t("wizard.product")} required error={productError}>
          <SelectField
            id="product_id"
            options={[
              ...products.map((p) => ({ value: p.id, label: `${productName(p, i18n.language)} (${p.code})` })),
              { value: "other", label: t("wizard.productOther") },
            ]}
            placeholder={t("wizard.productPlaceholder")}
            {...register("product_id")}
          />
        </FieldGroup>

        {formValues.product_id === "other" && (
          <FieldGroup htmlFor="product_text" label={t("wizard.productManual")} required>
            <input
              id="product_text"
              type="text"
              placeholder={t("wizard.productTextPlaceholder")}
              style={fieldStyle}
              {...register("product_text")}
            />
          </FieldGroup>
        )}

        <FieldGroup htmlFor="grade_text" label={t("wizard.grade")} error={gradeError}>
          <input id="grade_text" type="text" placeholder={t("wizard.gradePlaceholder")} style={fieldStyle} {...register("grade_text")} />
        </FieldGroup>

        <FieldGroup htmlFor="polymer_type" label={t("wizard.polymerType")}>
          <input id="polymer_type" type="text" placeholder={t("wizard.polymerTypePlaceholder")} style={fieldStyle} {...register("polymer_type")} />
        </FieldGroup>

        <FieldGroup
          htmlFor="volume"
          label={t("wizard.volume")}
          error={errors.volume?.message ? t(`error.${errors.volume.message}`, errors.volume.message) : undefined}
        >
          <input id="volume" type="number" inputMode="decimal" min="0.01" step="any" placeholder={t("wizard.volumePlaceholder")} style={fieldStyle} {...register("volume")} />
        </FieldGroup>

        <FieldGroup htmlFor="volume_unit" label={t("wizard.volumeUnit")}>
          <SelectField
            id="volume_unit"
            options={VOLUME_UNIT_VALUES.map((v) => ({ value: v, label: t(`wizard.volumeUnit_${v}`, v) }))}
            defaultValue={store.volume_unit}
            {...register("volume_unit")}
          />
        </FieldGroup>

        <button
          type="button"
          onClick={() =>
            void handleSubmit((data) => {
              persist(store, data);
              impactLight();
              navigate("/request/step/2");
            })()
          }
          style={{
            display: "block",
            width: "100%",
            minHeight: "44px",
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
          {t("wizard.next")}
        </button>
      </form>
    </div>
  );
}
