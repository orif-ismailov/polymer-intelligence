import { useTranslation } from "react-i18next";

import { PRODUCT_OTHER } from "@/entities/product";
import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import {
  Alert,
  Button,
  ShieldCheckIcon,
  SpecItem,
  SpecList,
} from "@/shared/ui";

import {
  COUNTED_STEPS,
  STEP_PREVIEW,
  type RequestDocKind,
} from "../model/constants";
import { resolvedCity, useRequestDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepPreviewProps {
  error: Error | null;
  isPending: boolean;
  onPublish: () => void;
  onEdit: () => void;
}

/**
 * Sheet 5 — «Проверьте и объявите». Summary of every choice, the visibility
 * note, and the amber Publish CTA the mockup paints specially.
 */
export function StepPreview({
  error,
  isPending,
  onPublish,
  onEdit,
}: StepPreviewProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const draft = useRequestDraft((s) => s.draft);

  const productName =
    draft.productChoice === PRODUCT_OTHER
      ? [draft.productText.trim(), draft.gradeText.trim()].filter(Boolean).join(" · ")
      : draft.productLabel || t("common.notSpecified");

  const volume = draft.volume
    ? `${draft.volume} ${draft.volumeUnit}`
    : t("common.notSpecified");

  const price = draft.targetPrice.trim()
    ? `≤ ${draft.targetPrice} ${draft.currency} / ${draft.volumeUnit}`
    : t("common.notSpecified");

  const city = resolvedCity(draft);
  const terms = [
    draft.incoterms,
    city,
    countryName(draft.destinationCountry, lang),
  ]
    .filter(Boolean)
    .join(", ");

  const docs =
    draft.requiredDocs.length > 0
      ? draft.requiredDocs
          .map((k: RequestDocKind) => t(`requestWizard.extra.doc.${k}`))
          .join(", ")
      : "—";

  const comment = draft.comment.trim() || draft.specs.trim() || "—";

  return (
    <div className="space-y-5" data-testid="request-wizard-step-5">
      <header>
        <p className="num text-xs text-text-muted">
          {t("requestWizard.stepOf", { current: STEP_PREVIEW, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">
          {t("requestWizard.preview.title")}
        </h2>
      </header>

      <div className="rounded-md border border-border bg-surface px-4 py-1">
        <SpecList variant="justified" columns={1}>
          <SpecItem label={t("requestWizard.preview.product")} value={productName} />
          <SpecItem label={t("requestWizard.preview.volume")} value={volume} numeric />
          <SpecItem label={t("requestWizard.preview.price")} value={price} numeric />
          <SpecItem label={t("requestWizard.preview.terms")} value={terms} />
          <SpecItem
            label={t("requestWizard.preview.delivery")}
            value={t(`requestWizard.params.deliveryOpt.${draft.deliveryBand}`)}
          />
          <SpecItem
            label={t("requestWizard.preview.validity")}
            value={t("requestWizard.params.validityOpt", { days: draft.validityDays })}
          />
          <SpecItem label={t("requestWizard.preview.comment")} value={comment} />
          <SpecItem label={t("requestWizard.preview.docs")} value={docs} />
          {/* Visibility is a property of the tender now, not a preference —
              so it belongs in the summary the buyer signs off on. */}
          <SpecItem
            label={t("requestWizard.preview.visibility")}
            value={t(`requestWizard.comm.visibility.${draft.visibility}.title`)}
          />
        </SpecList>
      </div>

      <div className="flex items-start gap-3 rounded-md border border-brand-line bg-brand-soft/20 px-4 py-3">
        <span className="mt-0.5 shrink-0 text-brand">
          <ShieldCheckIcon size={20} />
        </span>
        <p className="text-sm leading-relaxed text-text">
          {t(`requestWizard.preview.visibilityNote.${draft.visibility}`)}
        </p>
      </div>

      {error ? (
        <Alert tone="danger" title={t("errors.generic")}>
          {error.message || t("requestWizard.submitFailed")}
        </Alert>
      ) : null}

      <StepNav
        onNext={onPublish}
        disabled={isPending}
        loading={isPending}
        variant="gold"
        nextLabel={
          isPending ? t("common.saving") : t("requestWizard.preview.publish")
        }
        data-testid="request-wizard-publish"
      />

      <Button
        fullWidth
        size="lg"
        variant="outline"
        onClick={onEdit}
        disabled={isPending}
        data-testid="request-wizard-edit"
      >
        {t("common.edit")}
      </Button>
    </div>
  );
}
