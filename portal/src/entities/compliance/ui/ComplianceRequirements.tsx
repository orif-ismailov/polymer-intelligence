import { useTranslation } from "react-i18next";

import { Alert } from "@/shared/ui";

import type { MissingRequirement, RegulationLevel } from "../model/types";

interface ComplianceRequirementsProps {
  level: RegulationLevel;
  missing: MissingRequirement[];
  /** False while the gate is off — say "will be required", not "is blocked". */
  enforced?: boolean;
  substanceName?: string | null;
}

/**
 * "What this offer still needs before it can be published."
 *
 * Every line names the thing to go and get: a document kind, or the REGIME whose
 * licence is missing — four different bodies issue those, so "a licence" would
 * not be an instruction anyone could act on.
 */
export function ComplianceRequirements({
  level,
  missing,
  enforced = true,
  substanceName,
}: ComplianceRequirementsProps) {
  const { t } = useTranslation();
  if (missing.length === 0) return null;

  const banned = level === "prohibited";
  return (
    <Alert
      tone={banned ? "danger" : enforced ? "warning" : "info"}
      title={
        banned
          ? t("compliance.prohibitedTitle")
          : enforced
            ? t("compliance.blockedTitle")
            : t("compliance.wouldBlockTitle")
      }
    >
      <div className="space-y-2">
        {substanceName ? (
          <p className="text-sm">
            {t("compliance.substance")}: <span className="font-medium">{substanceName}</span>
          </p>
        ) : null}
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {missing.map((item, index) => (
            <li key={`${item.kind}-${item.detail ?? index}`}>
              {item.kind === "document"
                ? t("compliance.missingDocument", {
                    doc: t(`compliance.docKind.${item.detail}`, { defaultValue: item.detail }),
                  })
                : item.kind === "license"
                  ? t("compliance.missingLicense", {
                      regime: t(`compliance.regime.${item.detail}`, { defaultValue: item.detail }),
                    })
                  : t("compliance.missingProhibited", { act: item.detail ?? "—" })}
            </li>
          ))}
        </ul>
        <p className="text-xs opacity-80">
          {banned ? t("compliance.prohibitedHint") : t("compliance.blockedHint")}
        </p>
      </div>
    </Alert>
  );
}
