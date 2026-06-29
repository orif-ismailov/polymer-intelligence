/**
 * StatusChip — pill badge for request status (design-system §7 "Status badge").
 *
 * Uses both color AND text label — never color alone (UI-SPEC §Accessibility).
 * Maps each status onto the tinted --chip-* token pairs (ok / warn / down / neutral),
 * so it renders correctly in both dark and light themes.
 */

import { useTranslation } from "react-i18next";
import type { RequestStatus } from "../types";

type ChipTone = "ok" | "warn" | "down" | "neutral";

const STATUS_TONE: Record<string, ChipTone> = {
  new: "ok",
  viewed: "neutral",
  in_progress: "neutral",
  offer_sent: "ok",
  matched: "ok",
  closed: "neutral",
  cancelled: "down",
};

interface StatusChipProps {
  status: RequestStatus;
}

export default function StatusChip({ status }: StatusChipProps) {
  const { t } = useTranslation();
  const label = t(`status.${status}`, status);
  const tone = STATUS_TONE[status] ?? "neutral";

  return (
    <span
      role="status"
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        borderRadius: "var(--r-full)",
        fontSize: "12px",
        fontWeight: 600,
        backgroundColor: `var(--chip-${tone}-bg)`,
        color: `var(--chip-${tone}-fg)`,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}
