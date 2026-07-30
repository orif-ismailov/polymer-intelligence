import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import { Badge, Card, CardBody, FactoryIcon, GlobeIcon, PackageOpenIcon, RegistryIcon } from "@/shared/ui";

import type { ManufacturerCard as ManufacturerCardModel } from "../model/types";

interface ManufacturerListCardProps {
  manufacturer: ManufacturerCardModel;
  onOpen: () => void;
}

/** One row on the manufacturers directory (`docs/new-design/manufacturer_flow.jpeg`). */
export function ManufacturerListCard({ manufacturer, onOpen }: ManufacturerListCardProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const name = manufacturer.short_name ?? manufacturer.legal_name ?? "—";
  const country = countryName(manufacturer.jurisdiction, lang);
  const initial = name.slice(0, 1).toUpperCase();
  const countriesShown = manufacturer.export_countries.slice(0, 3);
  const extraCountries = manufacturer.export_countries.length - countriesShown.length;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      data-testid="manufacturer-card"
    >
      <Card className="transition-colors hover:border-brand-line">
        <CardBody className="space-y-3">
          <div className="flex items-start gap-3">
            {manufacturer.logo_url ? (
              <img
                src={manufacturer.logo_url}
                alt=""
                className="h-12 w-12 shrink-0 rounded-lg border border-border object-cover"
              />
            ) : (
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-info/20 text-lg font-bold text-info">
                {initial}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-text">{name}</p>
              <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-text-muted">
                <GlobeIcon size={12} />
                {country}
              </p>
            </div>
            {manufacturer.verified_at ? (
              <Badge variant="verified" className="shrink-0">
                {t("market.verified")}
              </Badge>
            ) : null}
          </div>

          {manufacturer.main_products ? (
            <p className="flex items-start gap-1.5 text-sm text-text-muted">
              <PackageOpenIcon size={14} className="mt-0.5 shrink-0" />
              <span className="line-clamp-2">{manufacturer.main_products}</span>
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-subtle">
            {manufacturer.production_type ? (
              <span className="flex items-center gap-1">
                <FactoryIcon size={12} />
                {manufacturer.production_type}
              </span>
            ) : null}
            {manufacturer.employees != null ? (
              <span className="num">{t("manufacturers.employeesShort", { count: manufacturer.employees })}</span>
            ) : null}
            {manufacturer.founded_year != null ? (
              <span className="num">{t("manufacturers.foundedShort", { year: manufacturer.founded_year })}</span>
            ) : null}
          </div>

          {countriesShown.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {countriesShown.map((code) => (
                <Badge key={code} tone="neutral">
                  {countryName(code, lang)}
                </Badge>
              ))}
              {extraCountries > 0 ? <Badge tone="neutral">+{extraCountries}</Badge> : null}
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
            <span className="flex items-center gap-1.5 text-xs text-text-subtle">
              <RegistryIcon size={14} />
              {manufacturer.iso_certification ?? t("manufacturers.noIso")}
            </span>
            {manufacturer.offer_count > 0 ? (
              <Badge tone="neutral">
                {t("manufacturers.offerCount", { count: manufacturer.offer_count })}
              </Badge>
            ) : null}
          </div>
        </CardBody>
      </Card>
    </button>
  );
}
