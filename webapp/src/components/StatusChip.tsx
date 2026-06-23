/**
 * StatusChip — pill badge for request status.
 *
 * Uses both color AND text label — never color alone (UI-SPEC §Accessibility).
 * Status→{bg,color} map per UI-SPEC §Color D-10.
 *
 * Background color is applied at 15% opacity via CSS color-mix.
 * Fallback for cancelled uses the sole permitted hardcoded hex #ef4444.
 */

import { useTranslation } from "react-i18next";
import type { RequestStatus } from "../types";

// D-10 status → chip styling map (UI-SPEC §Color, status chip color map)
interface ChipStyle {
  bgVar: string | null;
  colorVar: string | null;
  bgFallback: string;
  colorFallback: string;
}

const CHIP_MAP: Record<string, ChipStyle> = {
  new:         { bgVar: "--tg-theme-button-color", colorVar: "--tg-theme-button-color", bgFallback: "#10b981", colorFallback: "#10b981" },
  viewed:      { bgVar: "--tg-theme-hint-color",   colorVar: "--tg-theme-hint-color",   bgFallback: "#94a3b8", colorFallback: "#94a3b8" },
  in_progress: { bgVar: "--tg-theme-hint-color",   colorVar: "--tg-theme-hint-color",   bgFallback: "#94a3b8", colorFallback: "#94a3b8" },
  offer_sent:  { bgVar: "--tg-theme-link-color",   colorVar: "--tg-theme-link-color",   bgFallback: "#38bdf8", colorFallback: "#38bdf8" },
  matched:     { bgVar: "--tg-theme-button-color", colorVar: "--tg-theme-button-color", bgFallback: "#10b981", colorFallback: "#10b981" },
  closed:      { bgVar: "--tg-theme-hint-color",   colorVar: "--tg-theme-hint-color",   bgFallback: "#94a3b8", colorFallback: "#94a3b8" },
  cancelled:   { bgVar: null,                      colorVar: null,                      bgFallback: "#ef4444", colorFallback: "#ef4444" },
};

interface StatusChipProps {
  status: RequestStatus;
}

export default function StatusChip({ status }: StatusChipProps) {
  const { t } = useTranslation();
  const label = t(`status.${status}`, status);

  const chip: ChipStyle = CHIP_MAP[status] ?? CHIP_MAP["closed"]!;

  // For cancelled: #ef4444 at 15% opacity (sole permitted hardcoded hex)
  const bgColor = chip.bgVar
    ? `color-mix(in srgb, var(${chip.bgVar}, ${chip.bgFallback}) 15%, transparent)`
    : "rgba(239, 68, 68, 0.15)";

  const textColor = chip.colorVar
    ? `var(${chip.colorVar}, ${chip.colorFallback})`
    : "#ef4444";

  return (
    <span
      role="status"
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "12px",
        fontWeight: 500,
        backgroundColor: bgColor,
        color: textColor,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}
