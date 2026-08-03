import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { offerPhotoFiles } from "@/shared/config";
import { Badge, ImageIcon } from "@/shared/ui";

import { publicOfferImageUrl } from "../model/api";
import type { PublicOfferCard } from "../model/types";

/**
 * A catalog listing on the public storefront.
 *
 * An `<a>`, not a button with an onClick, and that is the whole reason this
 * component exists separately from the cabinet's `MarketOfferCard`: a crawler
 * follows hrefs. The cabinet card wraps everything in `<button onClick=
 * navigate>`, which is invisible to a crawler and unopenable in a new tab.
 */
export function PublicOfferTile({ offer }: { offer: PublicOfferCard }) {
  const { t } = useTranslation();
  const title = offer.product_text ?? offer.grade_text ?? t("public.offer.untitled");
  const subtitle = offer.product_text && offer.grade_text ? offer.grade_text : null;
  const location = [offer.warehouse_city, offer.country].filter(Boolean).join(", ");
  const cover = offerPhotoFiles(offer.files)[0] ?? null;

  return (
    <Link
      to={`/market/${offer.id}`}
      className="group flex h-full min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface transition-colors hover:border-brand-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
    >
      <div className="relative aspect-[4/3] w-full border-b border-border bg-surface-inset">
        {cover ? (
          <img
            src={publicOfferImageUrl(offer.id, cover.id)}
            alt={title}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-text-subtle">
            <ImageIcon size={28} />
          </div>
        )}
        {offer.polymer_type ? (
          <span className="absolute start-2 top-2 rounded-sm border border-border bg-bg/80 px-1.5 py-0.5 text-[11px] font-medium text-text-muted backdrop-blur">
            {offer.polymer_type}
          </span>
        ) : null}
      </div>

      <div className="flex flex-1 flex-col gap-2 px-2.5 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
        {/* Title and availability stack on a phone. Two-up the card is ~173px
            wide, and «В наличии» beside the grade left the grade about 80px —
            enough to truncate almost every one of them. */}
        <div className="flex flex-col items-start gap-1.5 sm:flex-row sm:items-start sm:justify-between sm:gap-2">
          <div className="min-w-0 max-w-full">
            <h3 className="truncate text-[13px] font-semibold text-text sm:text-sm">{title}</h3>
            {subtitle ? (
              <p className="truncate text-[11px] text-text-muted sm:text-xs">{subtitle}</p>
            ) : null}
          </div>
          <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
            {t(`availability.${offer.availability}`)}
          </Badge>
        </div>

        {/* `sm:leading-tight` on the price below is not decoration. A NAMED
            font-size utility sets a line-height too, so `sm:text-lg` lands in
            the `sm` layer AFTER the unprefixed `leading-tight` and quietly
            overrides it — 28px instead of 22.5px, which grew every desktop card
            by 5px and the page by 36px. Any `leading-*` has to be repeated at
            whatever breakpoint re-declares the size. Arbitrary sizes like
            `text-[13px]` set font-size only and need no repeat. */}
        <div>
          {offer.price == null ? (
            <p className="text-sm font-semibold text-text-muted sm:text-base">
              {t("public.offer.onRequest")}
            </p>
          ) : (
            <p className="num text-base font-semibold leading-tight text-brand sm:text-lg sm:leading-tight">
              {offer.price}{" "}
              <span className="text-xs font-medium text-text-muted sm:text-sm">
                {offer.currency}
                {offer.qty_unit ? `/${offer.qty_unit}` : ""}
              </span>
            </p>
          )}
          {offer.min_order_qty ? (
            <p className="num mt-0.5 text-[11px] text-text-muted sm:text-xs">
              {t("public.offer.moq")}: {offer.min_order_qty} {offer.qty_unit}
            </p>
          ) : null}
        </div>

        {/* `Badge` is `whitespace-nowrap shrink-0` on purpose — a chip that wraps
            to two lines breaks every card header it sits in. But «Проверено
            лабораторией» is wider than a 173px two-up card, so at that size it
            ran straight off the edge and got clipped by the card's own
            `overflow-hidden`, with no ellipsis to show anything was missing.
            Capping the pill and truncating inside it keeps the chip a chip. */}
        {offer.lab_verified || offer.has_lab_passport ? (
          <div className="flex min-w-0 flex-wrap gap-1.5">
            {offer.lab_verified ? (
              <Badge variant="lab-verified" className="min-w-0 max-w-full">
                <span className="min-w-0 truncate">{t("public.offer.labVerified")}</span>
              </Badge>
            ) : (
              <Badge tone="neutral" className="min-w-0 max-w-full">
                <span className="min-w-0 truncate">{t("public.offer.labPassport")}</span>
              </Badge>
            )}
          </div>
        ) : null}

        {/* Same reason as the title row: the seller line and the «Проверен»
            badge do not both fit on 173px, so on a phone the badge takes the
            line under the seller instead of squeezing it. */}
        <div className="mt-auto flex flex-col items-start gap-1.5 border-t border-border pt-2.5 sm:flex-row sm:items-end sm:justify-between sm:gap-2 sm:pt-3">
          <span className="min-w-0 max-w-full text-[11px] text-text-muted sm:text-xs">
            <span className="block truncate">{offer.display_name ?? "-"}</span>
            {location ? (
              <span className="block truncate text-text-subtle">{location}</span>
            ) : null}
          </span>
          {offer.company_verified ? (
            <Badge variant="verified" className="shrink-0">
              {t("public.offer.verified")}
            </Badge>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
