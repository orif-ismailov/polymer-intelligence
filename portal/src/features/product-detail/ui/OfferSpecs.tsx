import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";
import { countryName } from "@/shared/lib";
import { Badge, Card, CardBody, SpecItem, SpecList } from "@/shared/ui";

import type { ProductDetailOffer } from "../model/types";

/**
 * The «Характеристики» panel — the product's identity and terms.
 *
 * Shared by both tiers. On the storefront this is the keyword-bearing part of
 * the page (manufacturer, CAS, HS, applications), which is why the public sheet
 * renders it into the server HTML rather than leaving it behind a tab click.
 */
export function OfferSpecs({ offer }: { offer: ProductDetailOffer }) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);

  return (
    <Card>
      <CardBody>
        <SpecList>
          <SpecItem
            label={t("market.detail.manufacturer")}
            value={offer.manufacturer?.trim() || "—"}
          />
          <SpecItem label={t("market.detail.cas")} value={offer.cas_number?.trim() || "—"} />
          <SpecItem label={t("market.detail.hs")} value={offer.hs_code?.trim() || "—"} />
          <SpecItem
            label={t("market.detail.country")}
            value={offer.country ? countryName(offer.country, lang) : "—"}
          />
          <SpecItem label={t("market.warehouse")} value={offer.warehouse_city ?? "—"} />
          <SpecItem label={t("market.incoterms")} value={offer.incoterms} />
          {offer.lead_time_days != null ? (
            <SpecItem
              label={t("market.leadTimeShort")}
              value={t("market.leadTime", { count: offer.lead_time_days })}
              numeric
            />
          ) : null}
        </SpecList>
        <ChipList label={t("market.detail.keyProperties")} chips={offer.key_properties} />
        <ChipList label={t("market.detail.applications")} chips={offer.applications} />
      </CardBody>
    </Card>
  );
}

function ChipList({ label, chips }: { label: string; chips?: string[] }) {
  if (!chips || chips.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="mb-2 text-sm font-medium text-text">{label}</p>
      <ul className="flex flex-wrap gap-2">
        {chips.map((chip) => (
          <li key={chip}>
            <Badge tone="neutral">{chip}</Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
