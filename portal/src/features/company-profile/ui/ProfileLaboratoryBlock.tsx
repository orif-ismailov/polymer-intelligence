import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";

import {
  Badge,
  Card,
  CardBody,
  ClockIcon,
  FlaskIcon,
  ShieldCheckIcon,
  SpecItem,
  SpecList,
  SpecTile,
} from "@/shared/ui";

import type { LaboratoryProfileSnippet } from "../model/types";

interface ProfileLaboratoryBlockProps {
  laboratory: LaboratoryProfileSnippet;
}

/**
 * The laboratory half of «О компании» — the mockup's chips and three stat tiles.
 *
 * Everything here was already collected by the registration wizard and stored in
 * `companies.laboratory_profile`; none of it reached the public page, which
 * showed a lab the manufacturer fields instead (all blank, since a lab fills
 * none of them).
 *
 * Labels come from `wizard.laboratory.*` / `labRequest.*` — the SAME trees the
 * wizard and the request form write those keys from. A second copy of the
 * strings would drift the moment a method is renamed, and the value stored in
 * the blob is the key, so the two have to resolve through one map or the page
 * prints `iso_17025`.
 */
export function ProfileLaboratoryBlock({ laboratory }: ProfileLaboratoryBlockProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);

  const hasStats =
    laboratory.years_experience !== null ||
    laboratory.studies_completed !== null ||
    laboratory.avg_turnaround_days !== null;

  if (
    !hasStats &&
    laboratory.accreditations.length === 0 &&
    laboratory.methods.length === 0 &&
    !laboratory.description
  ) {
    return null;
  }

  return (
    <>
      {laboratory.description || laboratory.accreditations.length > 0 ? (
        <Card>
          <CardBody className="space-y-3">
            <h3 className="text-sm font-semibold text-text">
              {t("companyProfile.laboratory.aboutTitle")}
            </h3>
            {laboratory.description ? (
              <p className="text-sm leading-relaxed text-text">{laboratory.description}</p>
            ) : null}
            {laboratory.accreditations.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {laboratory.accreditations.map((key) => (
                  <Badge key={key} tone="success" icon={<ShieldCheckIcon size={12} />}>
                    {t(`companyProfile.laboratory.accreditationOptions.${key}`, {
                      defaultValue: key,
                    })}
                  </Badge>
                ))}
              </div>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      {hasStats ? (
        <Card>
          <CardBody>
            {/* The mockup's three tiles. `grid-cols-3` on every width: they are
                short values and stacking them wastes the fold. */}
            <div className="grid grid-cols-3 gap-3">
              {laboratory.years_experience !== null ? (
                <SpecTile
                  icon={<ShieldCheckIcon size={18} />}
                  label={t("companyProfile.laboratory.experience")}
                  value={t("companyProfile.laboratory.years", {
                    count: laboratory.years_experience,
                  })}
                  numeric
                />
              ) : null}
              {laboratory.studies_completed !== null ? (
                <SpecTile
                  icon={<FlaskIcon size={18} />}
                  label={t("companyProfile.laboratory.studies")}
                  value={t("companyProfile.laboratory.studiesValue", {
                    value: laboratory.studies_completed.toLocaleString(lang),
                  })}
                  numeric
                />
              ) : null}
              {laboratory.avg_turnaround_days !== null ? (
                <SpecTile
                  icon={<ClockIcon size={18} />}
                  label={t("companyProfile.laboratory.turnaround")}
                  value={t("companyProfile.laboratory.days", {
                    count: laboratory.avg_turnaround_days,
                  })}
                  numeric
                />
              ) : null}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {laboratory.methods.length > 0 ? (
        <Card>
          <CardBody className="space-y-3">
            <h3 className="text-sm font-semibold text-text">
              {t("companyProfile.laboratory.methodsTitle")}
            </h3>
            <div className="flex flex-wrap gap-2">
              {laboratory.methods.map((key) => (
                <Badge key={key} tone="neutral">
                  {t(`labRequest.methodOptions.${key}`, { defaultValue: key })}
                </Badge>
              ))}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {laboratory.city || laboratory.website ? (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-sm font-semibold text-text">
              {t("companyProfile.laboratory.detailsTitle")}
            </h3>
            <SpecList>
              {laboratory.city ? (
                <SpecItem
                  label={t("companyProfile.laboratory.city")}
                  value={laboratory.city}
                />
              ) : null}
              {laboratory.website ? (
                <SpecItem
                  label={t("companyProfile.laboratory.website")}
                  value={laboratory.website}
                />
              ) : null}
            </SpecList>
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
