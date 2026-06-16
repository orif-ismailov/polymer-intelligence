/**
 * ErrorBanner — full-width destructive notification banner.
 *
 * Sole use of hardcoded hex #ef4444 per UI-SPEC §Color (destructive-only exception).
 * Background at 10% opacity, text at full destructive color.
 *
 * The `message` prop accepts a pre-translated string (caller calls t('error.loadFailed')).
 */

import type { CSSProperties } from "react";

interface ErrorBannerProps {
  message: string;
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      style={{
        padding: "12px 16px",
        borderRadius: "8px",
        backgroundColor: "rgba(239, 68, 68, 0.10)", // #ef4444 at 10% — UI-SPEC §Color
        color: "#ef4444",
        fontSize: "13px",
        lineHeight: 1.4,
        marginBottom: "12px",
      } as CSSProperties}
    >
      {message}
    </div>
  );
}
