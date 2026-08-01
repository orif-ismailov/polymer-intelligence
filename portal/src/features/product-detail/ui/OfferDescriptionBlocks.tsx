import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { MarketOfferDetail, OfferFileRef } from "@/entities/market";
import { offerImageUrl } from "@/entities/market";
import { SampleRequestForm } from "@/features/sample-request";
import { coerceLang } from "@/shared/i18n";
import { cn, countryName, formatQty } from "@/shared/lib";
import {
  AlignLeftIcon,
  Button,
  Card,
  CardBody,
  CheckCircleIcon,
  ChevronRightIcon,
  DownloadIcon,
  FlaskIcon,
  GitCompareIcon,
  GlobeIcon,
  HashIcon,
  PackageOpenIcon,
  PdfIcon,
  SparkIcon,
  StarIcon,
} from "@/shared/ui";

import { SectionHeader } from "./SectionHeader";

interface OfferDescriptionBlocksProps {
  offer: MarketOfferDetail;
  documents: OfferFileRef[];
  passport: OfferFileRef | null;
  companyId: number | null;
  sampleSent: boolean;
  onSampleSent: () => void;
  onRequestSample: () => void;
}

function qtyLabel(
  value: string | number | null | undefined,
  unit: string,
  lang: string,
  fallback: string,
): string {
  if (value == null || value === "") return fallback;
  return formatQty(value, unit, lang);
}

/**
 * The long scroll under «Описание» — facts, offer type, samples, lab, seller,
 * compatibility CTA, and the horizontal documents strip.
 */
export function OfferDescriptionBlocks({
  offer,
  documents,
  passport,
  companyId,
  sampleSent,
  onSampleSent,
  onRequestSample,
}: OfferDescriptionBlocksProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const country = offer.country ? countryName(offer.country, lang) : "—";
  const inStock = offer.availability === "in_stock";

  return (
    <div className="space-y-4">
      <Card>
        <CardBody>
          {/* No `action` chevron: the mockup paints one, but there is no second
              screen for the basics block to open, and a chevron that goes nowhere
              is an affordance that lies. */}
          <SectionHeader title={t("market.detail.basics")} icon={<AlignLeftIcon size={16} />} />
          {offer.description ? (
            <p className="whitespace-pre-line text-sm leading-relaxed text-text">{offer.description}</p>
          ) : (
            <p className="text-sm text-text-muted">{t("market.noDescription")}</p>
          )}
          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <FactTile
              icon={<FlaskIcon size={14} />}
              label={t("market.detail.cas")}
              value={offer.cas_number?.trim() || "—"}
            />
            <FactTile
              icon={<HashIcon size={14} />}
              label={t("market.detail.hs")}
              value={offer.hs_code?.trim() || "—"}
            />
            <FactTile
              icon={<GlobeIcon size={14} />}
              label={t("market.detail.country")}
              value={country}
            />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <SectionHeader title={t("market.detail.offerType")} hint={t("market.detail.offerTypeHint")} />
          <div className="grid grid-cols-2 gap-2">
            <AvailabilityChip
              active={inStock}
              label={t("availability.in_stock")}
            />
            <AvailabilityChip
              active={!inStock}
              label={t("availability.on_order")}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Readout
              label={t("market.detail.qtyAvailable")}
              value={qtyLabel(offer.qty_available, offer.qty_unit, lang, "—")}
            />
            <Readout
              label={t("market.detail.moq")}
              value={qtyLabel(offer.min_order_qty, offer.qty_unit, lang, "—")}
            />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <SectionHeader title={t("market.detail.samples")} hint={t("market.detail.samplesHint")} />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <StatusLine
              ok={offer.samples_available}
              okLabel={t("market.detail.samplesAvailable")}
              noLabel={t("market.detail.samplesUnavailable")}
            />
            {offer.samples_available && !offer.is_own ? (
              <Button
                variant="outline"
                size="sm"
                className="w-full shrink-0 sm:w-auto"
                onClick={onRequestSample}
              >
                <PackageOpenIcon size={14} />
                {t("market.detail.requestSample")}
              </Button>
            ) : null}
          </div>
          {offer.samples_available && !offer.is_own && companyId != null ? (
            <div id="samples" className="mt-4 border-t border-border pt-4">
              {sampleSent ? (
                <p className="text-sm text-success">{t("samples.sentOk")}</p>
              ) : (
                <SampleRequestForm
                  offerId={offer.id}
                  companyId={companyId}
                  onSent={onSampleSent}
                />
              )}
            </div>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <SectionHeader
            title={t("market.detail.labPassport")}
            hint={t("market.detail.labPassportHint")}
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <StatusLine
              ok={offer.has_lab_passport || offer.lab_verified}
              okLabel={t("market.detail.labPassportPresent")}
              noLabel={t("market.detail.labPassportAbsent")}
            />
            {passport ? (
              <a
                href={offerImageUrl(offer.id, passport.id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex w-full shrink-0 items-center justify-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-text transition-colors hover:border-brand-line hover:text-brand sm:w-auto"
              >
                <DownloadIcon size={14} />
                {t("common.download")}
              </a>
            ) : null}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <SectionHeader title={t("market.seller")} hint={t("market.detail.sellerHint")} />
          {offer.seller_company_id != null ? (
            <Link
              to={`/cabinet/sellers/${offer.seller_company_id}?fromOffer=${offer.id}`}
              className="flex items-center gap-3 rounded-md border border-border bg-surface-2 px-3 py-3 transition-colors hover:border-brand-line hover:bg-surface"
              data-testid="product-detail-seller"
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-info/20 text-sm font-bold text-info">
                {(offer.display_name ?? "?").slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-text">{offer.display_name ?? "—"}</p>
                {offer.company_verified ? (
                  <p className="mt-0.5 flex items-center gap-1 text-xs text-brand">
                    <CheckCircleIcon size={12} />
                    {t("market.detail.verifiedSupplier")}
                  </p>
                ) : (
                  <p className="mt-0.5 text-xs text-text-muted">{t("market.notVerified")}</p>
                )}
                <p className="mt-1 flex items-center gap-1 text-xs text-text-subtle">
                  <StarIcon size={12} className="text-gold" />
                  {t("market.detail.ratingPending")}
                </p>
              </div>
              <ChevronRightIcon size={16} className="shrink-0 text-text-subtle" />
            </Link>
          ) : (
            <div className="flex items-center gap-3 rounded-md border border-border bg-surface-2 px-3 py-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-info/20 text-sm font-bold text-info">
                {(offer.display_name ?? "?").slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-text">{offer.display_name ?? "—"}</p>
                {offer.company_verified ? (
                  <p className="mt-0.5 flex items-center gap-1 text-xs text-brand">
                    <CheckCircleIcon size={12} />
                    {t("market.detail.verifiedSupplier")}
                  </p>
                ) : (
                  <p className="mt-0.5 text-xs text-text-muted">{t("market.notVerified")}</p>
                )}
                <p className="mt-1 flex items-center gap-1 text-xs text-text-subtle">
                  <StarIcon size={12} className="text-gold" />
                  {t("market.detail.ratingPending")}
                </p>
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card className="border-info/40">
        <CardBody className="space-y-3">
          <SectionHeader
            title={t("market.detail.compatibility")}
            icon={
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-info/15 text-info">
                <GitCompareIcon size={14} />
              </span>
            }
            hint={t("market.detail.compatibilityHint")}
          />
          <p className="text-sm text-text-muted">{t("market.detail.compatibilityBody")}</p>
          <Button variant="secondary" fullWidth disabled title={t("market.detail.comingSoon")}>
            <SparkIcon size={16} className="text-gold" />
            {t("market.detail.checkCompatibility")}
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <SectionHeader title={t("market.tabs.documents")} hint={t("market.detail.documentsHint")} />
          {documents.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {documents.map((file) => (
                <li key={file.id}>
                  <a
                    href={offerImageUrl(offer.id, file.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-text transition-colors hover:border-brand-line"
                  >
                    <PdfIcon size={14} className="text-danger" />
                    <span>{t(`market.detail.docChip.${file.kind}`, { defaultValue: file.file_name })}</span>
                    <DownloadIcon size={12} className="text-text-subtle" />
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-text-muted">{t("market.noDocuments")}</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function FactTile({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border bg-surface px-3 py-2.5">
      <span className="mt-0.5 shrink-0 text-text-subtle">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-text-muted">{label}</p>
        <p className="num truncate text-sm font-medium text-text">{value}</p>
      </div>
    </div>
  );
}

function AvailabilityChip({ active, label }: { active: boolean; label: string }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border px-3 py-3 text-sm font-medium",
        active
          ? "border-brand bg-brand-soft text-text"
          : "border-border bg-surface text-text-muted",
      )}
      aria-current={active || undefined}
    >
      {active ? (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand text-brand-fg">
          <CheckCircleIcon size={12} />
        </span>
      ) : (
        <span className="h-5 w-5 rounded-full border border-border" />
      )}
      {label}
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="mb-1.5 text-xs text-text-muted">{label}</p>
      <div className="num rounded-md border border-border bg-surface-inset px-3 py-2.5 text-sm font-medium text-text">
        {value}
      </div>
    </div>
  );
}

function StatusLine({
  ok,
  okLabel,
  noLabel,
}: {
  ok: boolean;
  okLabel: string;
  noLabel: string;
}) {
  return (
    <p className={cn("flex items-center gap-1.5 text-sm", ok ? "text-brand" : "text-text-muted")}>
      {ok ? <CheckCircleIcon size={14} /> : null}
      {ok ? okLabel : noLabel}
    </p>
  );
}
