import { useTranslation } from "react-i18next";

import type { LogisticsRequest } from "@/entities/logistics-request";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatQty } from "@/shared/lib";
import { Card, CardBody, SpecItem, SpecList, Stepper } from "@/shared/ui";

interface LogisticsRequestSummaryProps {
  request: LogisticsRequest;
  /** Show the buyer instead of the carrier — the carrier's view of the row. */
  perspective?: "buyer" | "carrier";
}

/**
 * One request, read back.
 *
 * Shared by the buyer's success sheet and both parties' detail page: the facts
 * are the same either way, and only the chrome around them differs (confetti and
 * CTAs there, a page header here). Two copies of this list would have drifted
 * the first time a field was added.
 *
 * The three dots are the request LIFECYCLE, which is what the mockup's stepper
 * actually depicts — the form is one screen, so a stepper above it would have
 * counted to three and never moved.
 */
const LIFECYCLE = ["submitted", "in_progress", "quoted"] as const;

export function LogisticsRequestSummary({
  request,
  perspective = "buyer",
}: LogisticsRequestSummaryProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);

  // `closed`/`rejected`/`viewed` are not on the rail: it shows progress toward a
  // quote, and `indexOf` returning -1 for them correctly pins the dot at stage 1
  // rather than inventing a fourth state.
  const stageIndex = Math.max(
    0,
    LIFECYCLE.indexOf(request.status as (typeof LIFECYCLE)[number]),
  );
  const steps = LIFECYCLE.map((key, i) => ({
    id: i + 1,
    label: t(`logisticsRequest.lifecycle.${key}`),
  }));

  // Country CODES are what the wire carries; printing them raw would put
  // «CN, Шанхай» on screen — the storage format, not a place name.
  const endpoint = (country: string, city: string | null) =>
    [country === "other" ? null : countryName(country, lang), city]
      .filter(Boolean)
      .join(", ");

  const counterparty =
    perspective === "carrier" ? request.buyer_name : request.logistics_name;

  return (
    <div className="space-y-5">
      <Stepper
        steps={steps}
        current={stageIndex + 1}
        // Explicit: left to itself `Stepper` assumes everything before `current`
        // is complete, which is right for a wizard someone walked through and
        // wrong for a state a request happens to be in.
        completedIds={steps.slice(0, stageIndex).map((s) => s.id)}
        variant="stacked"
      />

      <Card>
        <CardBody>
          <SpecList>
            <SpecItem label={t("logisticsRequest.number")} value={request.number} numeric />
            <SpecItem
              label={t(
                perspective === "carrier"
                  ? "logisticsRequest.buyer"
                  : "logisticsRequest.carrier",
              )}
              value={counterparty ?? "—"}
            />
            <SpecItem label={t("logisticsRequest.cargoName")} value={request.cargo_name} />
            <SpecItem
              label={t("logisticsRequest.volume")}
              value={formatQty(request.volume, request.volume_unit, lang)}
              numeric
            />
            {request.packaging_type ? (
              <SpecItem
                label={t("logisticsRequest.packaging")}
                value={t(`logisticsRequest.packagingOptions.${request.packaging_type}`, {
                  defaultValue: request.packaging_type,
                })}
              />
            ) : null}
            <SpecItem
              label={t("logisticsRequest.routeTitle")}
              value={`${endpoint(request.from_country, request.from_city)} → ${endpoint(
                request.to_country,
                request.to_city,
              )}`}
              span={2}
            />
            {request.special_requirements ? (
              <SpecItem
                label={t("logisticsRequest.requirements")}
                value={request.special_requirements}
                span={2}
              />
            ) : null}
            {/* Only useful to the side that has to call back. */}
            {perspective === "carrier" && request.contact_phone ? (
              <SpecItem
                label={t("logisticsRequest.contact")}
                value={request.contact_phone}
                numeric
              />
            ) : null}
          </SpecList>
        </CardBody>
      </Card>
    </div>
  );
}
