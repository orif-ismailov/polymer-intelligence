import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

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
  const cover = offer.files.find((f) => f.kind === "photo") ?? null;

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

      <div className="flex flex-1 flex-col gap-3 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-text">{title}</h3>
            {subtitle ? (
              <p className="truncate text-xs text-text-muted">{subtitle}</p>
            ) : null}
          </div>
          <Badge variant={offer.availability === "in_stock" ? "in-stock" : "on-order"}>
            {t(`availability.${offer.availability}`)}
          </Badge>
        </div>

        <div>
          {offer.price == null ? (
            <p className="text-base font-semibold text-text-muted">
              {t("public.offer.onRequest")}
            </p>
          ) : (
            <p className="num text-lg font-semibold leading-tight text-brand">
              {offer.price}{" "}
              <span className="text-sm font-medium text-text-muted">
                {offer.currency}
                {offer.qty_unit ? `/${offer.qty_unit}` : ""}
              </span>
            </p>
          )}
          {offer.min_order_qty ? (
            <p className="num mt-0.5 text-xs text-text-muted">
              {t("public.offer.moq")}: {offer.min_order_qty} {offer.qty_unit}
            </p>
          ) : null}
        </div>

        {offer.lab_verified || offer.has_lab_passport ? (
          <div className="flex flex-wrap gap-1.5">
            {offer.lab_verified ? (
              <Badge variant="lab-verified">{t("public.offer.labVerified")}</Badge>
            ) : (
              <Badge tone="neutral">{t("public.offer.labPassport")}</Badge>
            )}
          </div>
        ) : null}

        <div className="mt-auto flex items-end justify-between gap-2 border-t border-border pt-3">
          <span className="min-w-0 text-xs text-text-muted">
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
