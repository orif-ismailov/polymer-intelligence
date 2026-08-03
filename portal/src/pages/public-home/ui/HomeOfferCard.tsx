import { Bookmark } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { publicOfferImageUrl, type PublicOfferCard } from "@/entities/public";
import { offerPhotoFiles } from "@/shared/config";
import { countryFlag, countryName } from "@/shared/lib";
import { ImageIcon } from "@/shared/ui";

/**
 * Recommended-product card from `marketplace.jpeg` §4.
 *
 * The cover is a full-bleed 4:3 photo flush with the card's top corners — an
 * earlier pass drew it as a circle inset in a square well, which is both off the
 * mockup and the single biggest reason the section ran ~40% tall. The polymer
 * chip and the bookmark sit over it; below come title, seller, flag + country,
 * form/terms, price, and an outline "Связаться" beside a bookmark button.
 */
export function HomeOfferCard({ offer }: { offer: PublicOfferCard }) {
  const { t, i18n } = useTranslation();
  const flag = countryFlag(offer.country);
  const title = offer.product_text ?? offer.grade_text ?? t("public.offer.untitled");
  const grade = offer.product_text && offer.grade_text ? offer.grade_text : null;
  const cover = offerPhotoFiles(offer.files)[0] ?? null;
  const seller = offer.display_name ?? t("public.company.untitled");

  return (
    <article className="flex h-full min-w-0 flex-col overflow-hidden rounded-md border border-border bg-surface transition-colors hover:border-brand-line">
      <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden bg-surface-inset">
        {cover ? (
          <img
            src={publicOfferImageUrl(offer.id, cover.id)}
            alt={title}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-surface-2 text-text-subtle ring-1 ring-border">
            <ImageIcon size={24} />
          </span>
        )}
        {offer.polymer_type ? (
          <span className="absolute start-2 top-2 rounded-sm border border-border bg-bg/80 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-text-muted">
            {offer.polymer_type}
          </span>
        ) : null}
        <Link
          to={`/market/${offer.id}`}
          aria-label={t("public.home.saveOffer")}
          className="absolute end-2 top-2 flex h-9 w-9 items-center justify-center rounded-md border border-border bg-bg/70 text-text-muted transition-colors hover:border-brand-line hover:text-brand sm:h-8 sm:w-8"
        >
          <Bookmark size={15} strokeWidth={1.75} aria-hidden />
        </Link>
      </div>

      <div className="flex min-w-0 flex-1 flex-col p-2.5 sm:p-3">
        <Link to={`/market/${offer.id}`} className="min-w-0 focus-visible:outline-none">
          <h3 className="truncate text-[13px] font-semibold text-text hover:text-brand sm:text-[15px]">
            {grade ? `${title}` : title}
            {grade ? (
              <span className="mt-0.5 block truncate text-[11px] font-normal text-text-muted">
                {grade}
              </span>
            ) : null}
          </h3>
        </Link>
        <p className="mt-1 truncate text-[11px] text-text-muted sm:mt-1.5 sm:text-[12px]">
          {seller}
        </p>
        {offer.country ? (
          <p className="mt-1.5 flex items-center gap-1.5 truncate text-[11px] text-text-muted sm:mt-2">
            {flag ? (
              <span aria-hidden className="text-[13px] leading-none">
                {flag}
              </span>
            ) : null}
            {countryName(offer.country, i18n.language)}
          </p>
        ) : null}

        <dl className="mt-2 space-y-0.5 text-[11px] text-text-subtle sm:mt-2.5 sm:space-y-1">
          <div className="flex gap-1">
            <dt>{t("public.home.offerForm")}:</dt>
            <dd className="truncate text-text-muted">{t("public.home.offerFormGranules")}</dd>
          </div>
          {offer.incoterms ? (
            <div className="flex gap-1">
              <dt>{t("public.home.offerTerms")}:</dt>
              <dd className="truncate text-text-muted">{offer.incoterms}</dd>
            </div>
          ) : null}
        </dl>

        <p className="num mt-2 text-[14px] font-semibold tracking-tight text-text sm:mt-3 sm:text-[15px]">
          {offer.price == null ? (
            <span className="text-sm text-text-muted">{t("public.offer.onRequest")}</span>
          ) : (
            <>
              {offer.currency === "USD" ? "$" : ""}
              {Number(offer.price).toLocaleString(undefined, {
                maximumFractionDigits: 0,
              })}
              <span className="ms-1 text-[11px] font-medium text-text-muted">
                {offer.currency === "USD" ? "" : `${offer.currency} `}/{" "}
                {offer.qty_unit ?? "MT"}
              </span>
            </>
          )}
        </p>

        <div className="mt-auto flex items-center gap-2 pt-2.5 sm:pt-3">
          <Link
            to={`/market/${offer.id}`}
            className="inline-flex h-10 flex-1 items-center justify-center rounded-sm border border-brand text-[12px] font-medium text-brand transition-colors hover:bg-brand-soft active:scale-[0.98] sm:h-8"
          >
            {t("public.home.contact")}
          </Link>
          {/*
            Hidden on a phone, where the card is 174px wide and this is the
            SECOND bookmark on it — the first sits over the photo, and both
            resolve to the same listing. Two controls left the primary action
            ~130px; one leaves it the full width. From `sm` the card is wide
            enough for the pair the mockup draws, so desktop is untouched.
          */}
          <Link
            to={`/market/${offer.id}`}
            aria-label={t("public.home.saveOffer")}
            className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-brand text-brand transition-colors hover:bg-brand-soft sm:inline-flex"
          >
            <Bookmark size={15} strokeWidth={1.75} aria-hidden />
          </Link>
        </div>
      </div>
    </article>
  );
}
