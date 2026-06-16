/**
 * RequestCard — tap target for a single request in the MyRequests (C-06) list.
 *
 * Layout: request number (15px/600) | StatusChip | product display | date
 * Touch target: ≥44px height (UI-SPEC §Accessibility, WCAG 2.5.5).
 * Navigates to /requests/{id} on tap.
 */

import type { CSSProperties } from "react";
import StatusChip from "./StatusChip";
import { formatTashkent } from "../util/datetime";
import type { RequestOut } from "../types";

interface RequestCardProps {
  request: RequestOut;
  onClick: (id: number) => void;
}

export default function RequestCard({ request, onClick }: RequestCardProps) {
  const dateStr = formatTashkent(request.created_at);

  return (
    <button
      type="button"
      onClick={() => onClick(request.id)}
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100%",
        minHeight: "44px",
        padding: "12px 16px",
        borderRadius: "12px",
        backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
        border: "none",
        cursor: "pointer",
        textAlign: "left",
        marginBottom: "12px",
        boxSizing: "border-box" as const,
        gap: "6px",
      } as CSSProperties}
      aria-label={`Заявка ${request.number}`}
    >
      {/* Row 1: request number + chip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "8px",
        } as CSSProperties}
      >
        <span
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: "var(--tg-theme-text-color, #f8fafc)",
          } as CSSProperties}
        >
          {request.number}
        </span>
        <StatusChip status={request.status} />
      </div>

      {/* Row 2: date */}
      <span
        style={{
          fontSize: "13px",
          color: "var(--tg-theme-hint-color, #94a3b8)",
        } as CSSProperties}
      >
        {dateStr}
      </span>
    </button>
  );
}
