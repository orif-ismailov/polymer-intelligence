import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import {
  BoxIcon,
  Card,
  CardBody,
  GlobeIcon,
  IconTile,
  NodesIcon,
  ShieldCheckIcon,
  ShieldIcon,
  SpecItem,
  SpecList,
  SpecTile,
  TruckIcon,
  UsersIcon,
  WarehouseIcon,
} from "@/shared/ui";

import type { LogisticsProfileSnippet } from "../model/types";

interface ProfileLogisticsBlockProps {
  logistics: LogisticsProfileSnippet;
}

/**
 * One icon per capability, so the list reads as five different things a carrier
 * owns rather than five copies of the same badge. Keys are the wizard's
 * `LOGISTICS_CAPABILITIES`; anything unmapped falls back to the warehouse
 * glyph, which is the neutral member of the set.
 */
const CAPABILITY_ICONS: Record<string, ReactNode> = {
  own_trucks: <TruckIcon size={18} />,
  own_rail_wagons: <NodesIcon size={18} />,
  sea_containers: <BoxIcon size={18} />,
  storage_facilities: <WarehouseIcon size={18} />,
  customs_warehouse: <ShieldCheckIcon size={18} />,
  foreign_offices: <GlobeIcon size={18} />,
  customs_brokers: <UsersIcon size={18} />,
};

/**
 * The carrier half of «О компании» — the 2×2 fact grid and «Наши возможности».
 *
 * Everything here was already being collected by the registration wizard and
 * stored in `companies.logistics_profile`; none of it reached the public page,
 * which showed a carrier the manufacturer fields instead (all blank, since a
 * carrier fills none of them).
 *
 * Labels come from `wizard.logistics.*` — the SAME tree the wizard writes those
 * keys from. That is deliberate rather than convenient: a second copy of the
 * strings would drift the moment an option is renamed, and the value stored in
 * the blob is the key, so the two have to resolve through one map or the page
 * prints `international_road`.
 */
export function ProfileLogisticsBlock({ logistics }: ProfileLogisticsBlockProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);

  const serviceLabels = logistics.services.map((key) =>
    t(`wizard.logistics.services.options.${key}`, { defaultValue: key }),
  );
  const cargoLabels = logistics.cargo_types.map((key) =>
    t(`wizard.logistics.specialization.cargo.${key}`, { defaultValue: key }),
  );
  const routeLabels = logistics.popular_routes.map((key) =>
    t(`wizard.logistics.geography.routes.${key}`, { defaultValue: key }),
  );

  // «Страны работы» is both ends of the lane in one cell, the way the mockup
  // draws it — a carrier's reach reads as one fact, not as two lists.
  const countryKeys = Array.from(
    new Set([...logistics.from_countries, ...logistics.to_countries]),
  );
  // `countryName` is `Intl.DisplayNames`, so the codes localise for free and in
  // every language the portal ships — the same helper `ProfileHeader` uses for
  // the jurisdiction. Only the wizard's `"other"` escape hatch needs a string.
  const countryLabels = countryKeys.map((key) =>
    key === "other"
      ? t("wizard.logistics.geography.countries.other", { defaultValue: key })
      : countryName(key, lang),
  );

  const hasFacts =
    countryLabels.length > 0 ||
    serviceLabels.length > 0 ||
    logistics.years_experience !== null ||
    logistics.projects_completed !== null;

  if (!hasFacts && logistics.capabilities.length === 0 && !logistics.description) {
    return null;
  }

  return (
    <>
      {logistics.description ? (
        <Card>
          <CardBody className="space-y-3">
            <h3 className="text-sm font-semibold text-text">
              {t("companyProfile.logistics.aboutTitle")}
            </h3>
            <p className="text-sm leading-relaxed text-text">{logistics.description}</p>
          </CardBody>
        </Card>
      ) : null}

      {hasFacts ? (
        <Card>
          <CardBody>
            {/* Two columns on every width: the mockup's 2×2, and four one-line
                cells stacked would push «Наши возможности» below the fold. */}
            <div className="grid grid-cols-2 gap-3">
              {countryLabels.length > 0 ? (
                <SpecTile
                  icon={<GlobeIcon size={18} />}
                  label={t("companyProfile.logistics.countries")}
                  value={countryLabels.join(", ")}
                />
              ) : null}
              {serviceLabels.length > 0 ? (
                <SpecTile
                  icon={<TruckIcon size={18} />}
                  label={t("companyProfile.logistics.services")}
                  value={serviceLabels.join(", ")}
                />
              ) : null}
              {logistics.years_experience !== null ? (
                <SpecTile
                  icon={<ShieldIcon size={18} />}
                  label={t("companyProfile.logistics.experience")}
                  value={t("companyProfile.logistics.years", {
                    count: logistics.years_experience,
                  })}
                  numeric
                />
              ) : null}
              {logistics.projects_completed !== null ? (
                <SpecTile
                  icon={<BoxIcon size={18} />}
                  label={t("companyProfile.logistics.projects")}
                  // Grouped («1 200+», not «1200+») — the figure is the whole
                  // point of the cell and `Intl` knows the separator per locale.
                  value={t("companyProfile.logistics.projectsValue", {
                    value: logistics.projects_completed.toLocaleString(lang),
                  })}
                  numeric
                />
              ) : null}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {logistics.capabilities.length > 0 ? (
        <Card>
          <CardBody className="space-y-3">
            <h3 className="text-sm font-semibold text-text">
              {t("companyProfile.logistics.capabilitiesTitle")}
            </h3>
            <ul className="space-y-3">
              {logistics.capabilities.map((key) => (
                <li key={key} className="flex items-start gap-3">
                  {/* A real photo when the carrier uploaded one, the glyph
                      otherwise — the mockup draws thumbnails, but a profile with
                      none must still read as a list rather than as gaps. */}
                  {logistics.capability_images?.[key] ? (
                    <img
                      src={logistics.capability_images[key]}
                      alt=""
                      className="h-12 w-16 shrink-0 rounded-md border border-border object-cover"
                    />
                  ) : (
                    <IconTile tone="brand" size="md">
                      {CAPABILITY_ICONS[key] ?? <WarehouseIcon size={18} />}
                    </IconTile>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-text">
                      {t(`wizard.logistics.specialization.capabilities.${key}`, {
                        defaultValue: key,
                      })}
                    </p>
                    {/* A one-line blurb per capability, so the row reads like the
                        mockup's «Автопарк / Современные тягачи и контейнеровозы»
                        rather than as a bare checklist item. */}
                    <p className="text-xs leading-relaxed text-text-muted">
                      {t(`companyProfile.logistics.capabilityBlurb.${key}`, {
                        defaultValue: "",
                      })}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {cargoLabels.length > 0 || routeLabels.length > 0 || logistics.tariff_model ? (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-sm font-semibold text-text">
              {t("companyProfile.logistics.detailsTitle")}
            </h3>
            <SpecList>
              {cargoLabels.length > 0 ? (
                <SpecItem
                  label={t("companyProfile.logistics.cargo")}
                  value={cargoLabels.join(", ")}
                />
              ) : null}
              {routeLabels.length > 0 ? (
                <SpecItem
                  label={t("companyProfile.logistics.routes")}
                  value={routeLabels.join(", ")}
                />
              ) : null}
              {logistics.tariff_model ? (
                <SpecItem
                  label={t("companyProfile.logistics.tariff")}
                  value={t(`wizard.logistics.tariffs.models.${logistics.tariff_model}`, {
                    defaultValue: logistics.tariff_model,
                  })}
                />
              ) : null}
              {logistics.city ? (
                <SpecItem label={t("companyProfile.logistics.city")} value={logistics.city} />
              ) : null}
            </SpecList>
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
