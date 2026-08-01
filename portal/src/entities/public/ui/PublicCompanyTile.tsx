import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Badge, RegistryIcon } from "@/shared/ui";

import type { PublicCompanyCard } from "../model/types";

/**
 * A company row in a public directory.
 *
 * Same reason as `PublicOfferTile` for being a link rather than a click handler:
 * a directory whose entries are not hrefs is a directory a crawler reads as a
 * single page with no children.
 */
export function PublicCompanyTile({
  company,
  slug,
}: {
  company: PublicCompanyCard;
  slug: string;
}) {
  const { t } = useTranslation();
  const name = company.short_name ?? company.legal_name ?? t("public.company.untitled");

  return (
    <Link
      to={`/${slug}/${company.id}`}
      className="group flex h-full min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-brand-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
    >
      <div className="flex min-w-0 items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-surface-inset">
          {company.logo_url ? (
            <img
              src={company.logo_url}
              alt=""
              loading="lazy"
              className="h-full w-full object-contain"
            />
          ) : (
            <RegistryIcon size={20} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-text">{name}</h3>
          {company.legal_address ? (
            <p className="truncate text-xs text-text-muted">{company.legal_address}</p>
          ) : (
            <p className="text-xs text-text-muted">{company.jurisdiction}</p>
          )}
        </div>
        <Badge variant="verified" className="shrink-0">
          {t("public.offer.verified")}
        </Badge>
      </div>

      {company.main_products ? (
        <p className="line-clamp-2 text-xs text-text-muted">{company.main_products}</p>
      ) : null}

      <dl className="mt-auto grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border pt-3 text-xs">
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-text-subtle">{t("public.company.offers")}</dt>
          <dd className="num font-medium text-text">{company.offer_count}</dd>
        </div>
        {company.founded_year ? (
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-text-subtle">{t("public.company.founded")}</dt>
            <dd className="num font-medium text-text">{company.founded_year}</dd>
          </div>
        ) : null}
        {company.employees ? (
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-text-subtle">{t("public.company.employees")}</dt>
            <dd className="num font-medium text-text">{company.employees}</dd>
          </div>
        ) : null}
        {company.iso_certification ? (
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-text-subtle">{t("public.company.iso")}</dt>
            <dd className="truncate font-medium text-text">{company.iso_certification}</dd>
          </div>
        ) : null}
      </dl>
    </Link>
  );
}
