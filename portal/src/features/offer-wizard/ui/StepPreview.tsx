import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import { offerApi } from "@/entities/offer";
import { PRODUCT_OTHER, productLabel, useProducts } from "@/entities/product";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatMoney, formatQty } from "@/shared/lib";
import {
  Alert,
  Badge,
  BoxIcon,
  Button,
  CheckCircleIcon,
  FactoryIcon,
  FlaskIcon,
  GlobeIcon,
  ImageIcon,
  BanknoteIcon,
  RocketIcon,
  SpecItem,
  SpecList,
  StepPanel,
  TruckIcon,
  WarehouseIcon,
} from "@/shared/ui";

import {
  DISPATCH_BANDS,
  OFFER_DOCUMENT_KINDS,
  type OfferDocumentKind,
} from "../model/constants";
import { useOfferDraft, warehouseValue } from "../model/draftStore";
import type { SubmitProgress } from "../model/useSubmitOffer";

/** Rail / collage stop for the preview — the mockup's «7 Публикация». */
const PREVIEW_STEP = 7;

interface StepPreviewProps {
  companyId: number;
  isEdit: boolean;
  progress: SubmitProgress;
  error: Error | null;
  onPublish: () => void;
  onBack: () => void;
}

/**
 * The cover picture, from whichever side of the draft holds it — a staged file
 * has an object URL already, a file on the server needs the owner-scoped Blob
 * fetch (the token is memory-only, so `<img src>` would go out unauthenticated).
 */
function CoverPhoto({ companyId }: { companyId: number }) {
  const { t } = useTranslation();
  const photos = useOfferDraft((s) => s.photos);
  const serverFiles = useOfferDraft((s) => s.serverFiles);
  const offerId = useOfferDraft((s) => s.offerId);
  const [serverUrl, setServerUrl] = useState<string | null>(null);

  const serverPhotos = serverFiles.filter((f) => f.kind === "image");
  const total = serverPhotos.length + photos.length;
  const firstServer = serverPhotos[0] ?? null;

  useEffect(() => {
    if (!firstServer || offerId == null) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    void offerApi
      .fileBlob(companyId, offerId, firstServer.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setServerUrl(objectUrl);
      })
      .catch(() => {
        /* falls back to the placeholder */
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [companyId, offerId, firstServer]);

  const src = serverUrl ?? photos[0]?.previewUrl ?? null;

  return (
    <div className="relative aspect-[4/3] w-full overflow-hidden rounded-md border border-border bg-surface-inset">
      {src ? (
        <img src={src} alt="" className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-text-subtle">
          <ImageIcon size={28} />
          <span className="text-xs">{t("offerWizard.preview.noPhoto")}</span>
        </div>
      )}
      {total > 0 ? (
        <span className="num absolute bottom-2 left-2 rounded-full bg-overlay px-2 py-0.5 text-xs font-medium text-text">
          1/{total}
        </span>
      ) : null}
    </div>
  );
}

/**
 * The «Публикация» sheet: the card as a buyer will see it, over the green CTA.
 *
 * Neon green (not gold) — the collage paints «Опубликовать товар» the same
 * colour as every other primary action. In edit mode the offer is already
 * public (or queued), so the button says «Сохранить».
 */
export function StepPreview({
  companyId,
  isEdit,
  progress,
  error,
  onPublish,
  onBack,
}: StepPreviewProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const draft = useOfferDraft((s) => s.draft);
  const documents = useOfferDraft((s) => s.documents);
  const serverFiles = useOfferDraft((s) => s.serverFiles);
  const labPassport = useOfferDraft((s) => s.labPassport);
  const products = useProducts();

  const catalogRow = (products.data ?? []).find((p) => String(p.id) === draft.productChoice);
  const name =
    draft.productChoice === PRODUCT_OTHER
      ? draft.productText.trim()
      : catalogRow
        ? productLabel(catalogRow, lang)
        : t("common.notSpecified");

  const hasPassport =
    labPassport !== null || serverFiles.some((f) => f.kind === "lab_passport");

  const attachedDocs = OFFER_DOCUMENT_KINDS.filter(
    (kind: OfferDocumentKind) =>
      documents[kind] != null || serverFiles.some((f) => f.kind === kind),
  );

  const dispatchLabel = t(`offerWizard.availability.dispatch.${draft.dispatchBand}`);
  const leadDays = DISPATCH_BANDS.find((b) => b.id === draft.dispatchBand)?.days ?? null;
  const onOrder = draft.availability === "on_order";

  const busy = progress.phase !== "idle";
  const busyLabel =
    progress.phase === "uploading"
      ? t("offerWizard.preview.uploading", {
          done: progress.uploaded,
          total: progress.total,
        })
      : t("offerWizard.preview.publishing");

  return (
    <StepPanel
      step={PREVIEW_STEP}
      title={t("offerWizard.preview.title")}
      data-testid="offer-wizard-step-preview"
    >
      <CoverPhoto companyId={companyId} />

      <div className="mt-4">
        <h3 className="text-xl font-semibold text-text" data-testid="offer-wizard-preview-name">
          {name}
        </h3>
        <div className="mt-2 flex flex-wrap gap-2">
          <Badge variant={onOrder ? "on-order" : "in-stock"}>
            {t(`availability.${draft.availability}`)}
          </Badge>
          {hasPassport ? (
            <Badge tone="neutral" icon={<FlaskIcon />}>
              {t("lab.badge.passport")}
            </Badge>
          ) : null}
        </div>
        {draft.category ? (
          <p className="mt-1.5 text-sm text-text-muted">{draft.category}</p>
        ) : null}
      </div>

      <SpecList variant="justified" columns={1} className="mt-4">
        <SpecItem
          label={
            <span className="inline-flex items-center gap-1.5">
              <FactoryIcon size={13} />
              {t("offerWizard.basics.manufacturer")}
            </span>
          }
          value={draft.manufacturer || t("common.notSpecified")}
        />
        <SpecItem
          label={
            <span className="inline-flex items-center gap-1.5">
              <GlobeIcon size={13} />
              {t("offerWizard.preview.country")}
            </span>
          }
          value={countryName(draft.originCountry, lang)}
        />
        <SpecItem
          label={
            <span className="inline-flex items-center gap-1.5">
              <BoxIcon size={13} />
              {t("offerWizard.preview.qty")}
            </span>
          }
          value={onOrder ? t("offerWizard.preview.onRequest") : formatQty(draft.qty, draft.qtyUnit, lang)}
          numeric
        />
        <SpecItem
          label={
            <span className="inline-flex items-center gap-1.5">
              <BanknoteIcon size={13} />
              {t("offers.price")}
            </span>
          }
          value={
            onOrder
              ? t("offerWizard.preview.onRequest")
              : `${formatMoney(draft.price, draft.currency, lang)} / ${draft.qtyUnit}`
          }
          numeric
        />
        <SpecItem
          label={
            <span className="inline-flex items-center gap-1.5">
              <WarehouseIcon size={13} />
              {t("offerWizard.availability.warehouse")}
            </span>
          }
          value={warehouseValue(draft) || t("common.notSpecified")}
        />
        <SpecItem
          label={
            <span className="inline-flex items-center gap-1.5">
              <TruckIcon size={13} />
              {t("offerWizard.availability.dispatch.label")}
            </span>
          }
          value={leadDays == null ? t("common.notSpecified") : dispatchLabel}
        />
      </SpecList>

      {/* The two chip rows the mockup closes the card with: which documents are
          attached, and what the seller is ready to do. */}
      {attachedDocs.length > 0 ? (
        <ul className="mt-4 flex flex-wrap gap-2">
          {attachedDocs.map((kind) => (
            <li key={kind}>
              <Badge tone="brand" icon={<CheckCircleIcon />}>
                {t(`offerWizard.documents.short.${kind}`)}
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}

      <ul className="mt-2 flex flex-wrap gap-2">
        {draft.samplesAvailable ? (
          <li>
            <Badge tone="neutral">{t("offerWizard.preview.samplesAvailable")}</Badge>
          </li>
        ) : null}
        {draft.acceptsContract || draft.acceptsEscrow ? (
          <li>
            <Badge tone="neutral">
              {[
                draft.acceptsContract ? t("offerWizard.preview.dDoc") : null,
                draft.acceptsEscrow ? t("offerWizard.preview.escrow") : null,
              ]
                .filter(Boolean)
                .join(" / ")}
            </Badge>
          </li>
        ) : null}
      </ul>

      {error ? (
        <Alert tone="danger" className="mt-4" title={t("errors.generic")}>
          {error.message}
        </Alert>
      ) : null}

      <div className="mt-6 flex gap-3">
        <Button variant="ghost" size="lg" onClick={onBack} disabled={busy} className="min-w-24">
          {t("common.back")}
        </Button>
        <Button
          size="lg"
          variant="primary"
          loading={busy}
          onClick={onPublish}
          className="flex-1"
          data-testid="offer-wizard-publish"
        >
          {busy ? busyLabel : null}
          {busy ? null : <RocketIcon size={16} />}
          {busy ? null : isEdit ? t("common.save") : t("offerWizard.preview.publish")}
        </Button>
      </div>
    </StepPanel>
  );
}
