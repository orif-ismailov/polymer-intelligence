/**
 * StatusTimeline — vertical list of request status history rows.
 *
 * Displays each StatusHistory entry (from_status → to_status) with
 * Asia/Tashkent timestamps via formatTashkent (DEC-tz-handling, D-11).
 *
 * Used by RequestDetail (C-07).
 */

import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { formatTashkent } from "../util/datetime";
import type { StatusHistory, RequestStatus } from "../types";

interface StatusTimelineProps {
  history: StatusHistory[];
}

/** Map internal status to i18n key for label display */
function statusLabel(t: (key: string, fallback: string) => string, status: RequestStatus | null): string {
  if (!status) return "—";
  return t(`status.${status}`, status);
}

export default function StatusTimeline({ history }: StatusTimelineProps) {
  const { t } = useTranslation();

  return (
    <div>
      <h3
        style={{
          margin: "0 0 12px",
          fontSize: "15px",
          fontWeight: 600,
          color: "var(--tg-theme-text-color, #f8fafc)",
        } as CSSProperties}
      >
        {t("requestDetail.history")}
      </h3>

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" } as CSSProperties}>
        {history.map((row, idx) => (
          <div
            key={idx}
            style={{
              padding: "10px 12px",
              borderRadius: "8px",
              backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
            } as CSSProperties}
          >
            {/* Status transition */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                marginBottom: "4px",
              } as CSSProperties}
            >
              {row.from_status && (
                <>
                  <span
                    style={{
                      fontSize: "13px",
                      color: "var(--tg-theme-hint-color, #94a3b8)",
                    } as CSSProperties}
                  >
                    {statusLabel(t, row.from_status)}
                  </span>
                  <span
                    style={{
                      fontSize: "13px",
                      color: "var(--tg-theme-hint-color, #94a3b8)",
                    } as CSSProperties}
                  >
                    →
                  </span>
                </>
              )}
              <span
                style={{
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "var(--tg-theme-text-color, #f8fafc)",
                } as CSSProperties}
              >
                {statusLabel(t, row.to_status)}
              </span>
            </div>

            {/* Timestamp in Asia/Tashkent */}
            <span
              style={{
                fontSize: "12px",
                color: "var(--tg-theme-hint-color, #94a3b8)",
              } as CSSProperties}
            >
              {formatTashkent(row.created_at)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
