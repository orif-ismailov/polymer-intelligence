import { useTranslation } from "react-i18next";

import { Badge } from "@/shared/ui";
import type { BadgeTone } from "@/shared/ui";

import type { RegulationLevel } from "../model/types";

/**
 * How tightly a substance is regulated.
 *
 * Tones are meaning-first: an unregulated substance is not "good news" worth a
 * green pill, so `free` stays neutral and only the levels that cost the seller
 * something are coloured.
 */
const TONES: Record<RegulationLevel, BadgeTone> = {
  free: "neutral",
  docs_required: "info",
  license_required: "warning",
  prohibited: "danger",
};

export function RegulationBadge({ level }: { level: RegulationLevel }) {
  const { t } = useTranslation();
  return <Badge tone={TONES[level]}>{t(`compliance.level.${level}`)}</Badge>;
}
