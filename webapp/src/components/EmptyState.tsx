/**
 * EmptyState — illustration-free empty state component.
 *
 * Displays a heading, optional body text, and an optional CTA button.
 * Used by MyRequests (C-06) and Notifications (C-08).
 *
 * All copy comes via the `t()` key prop — never hardcoded (UI-SPEC §Copywriting).
 */

import type { CSSProperties } from "react";

interface EmptyStateProps {
  heading: string;
  body?: string;
  cta?: string;
  onCta?: () => void;
}

export default function EmptyState({ heading, body, cta, onCta }: EmptyStateProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 16px",
        textAlign: "center",
      }}
    >
      <h2
        style={{
          margin: "0 0 8px",
          fontSize: "15px",
          fontWeight: 600,
          color: "var(--tg-theme-text-color, #f8fafc)",
        } as CSSProperties}
      >
        {heading}
      </h2>
      {body && (
        <p
          style={{
            margin: "0 0 24px",
            fontSize: "13px",
            color: "var(--tg-theme-hint-color, #94a3b8)",
            lineHeight: 1.4,
          } as CSSProperties}
        >
          {body}
        </p>
      )}
      {cta && onCta && (
        <button
          type="button"
          onClick={onCta}
          style={{
            display: "inline-block",
            minHeight: "44px",
            padding: "12px 20px",
            borderRadius: "8px",
            backgroundColor: "var(--tg-theme-button-color, #10b981)",
            color: "var(--tg-theme-button-text-color, #ffffff)",
            border: "none",
            fontSize: "14px",
            fontWeight: 600,
            cursor: "pointer",
            boxSizing: "border-box" as const,
          } as CSSProperties}
        >
          {cta}
        </button>
      )}
    </div>
  );
}
