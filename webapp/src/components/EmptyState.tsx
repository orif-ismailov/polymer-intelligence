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
          color: "var(--text)",
        } as CSSProperties}
      >
        {heading}
      </h2>
      {body && (
        <p
          style={{
            margin: "0 0 24px",
            fontSize: "13px",
            color: "var(--text-muted)",
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
            minHeight: "48px",
            padding: "12px 24px",
            borderRadius: "var(--r-md)",
            backgroundColor: "var(--green)",
            color: "var(--green-on)",
            border: "none",
            fontSize: "16px",
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
