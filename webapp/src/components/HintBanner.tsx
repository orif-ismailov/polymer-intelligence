/**
 * HintBanner — soft informational banner (design-system §7 "Hint banner").
 *
 * --surface-2 bg + leading icon + caption text. Used for "Не знаете точную
 * марку?" (Step 1) and the "Ваши данные защищены" reassurance (Step 4 / How-it-works).
 * `tone="ok"` tints it green for the data-protection note.
 */

import { Info, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

interface HintBannerProps {
  children: ReactNode;
  tone?: "info" | "ok";
}

export default function HintBanner({ children, tone = "info" }: HintBannerProps) {
  const ok = tone === "ok";
  const Icon = ok ? ShieldCheck : Info;
  return (
    <div
      style={{
        display: "flex",
        gap: "10px",
        alignItems: "flex-start",
        padding: "12px 14px",
        borderRadius: "var(--r-md)",
        background: ok ? "var(--chip-ok-bg)" : "var(--surface-2)",
        marginBottom: "16px",
      }}
    >
      <Icon
        size={18}
        color={ok ? "var(--chip-ok-fg)" : "var(--text-muted)"}
        style={{ flex: "0 0 auto", marginTop: "1px" }}
        aria-hidden="true"
      />
      <span style={{ fontSize: "12px", lineHeight: 1.5, color: ok ? "var(--chip-ok-fg)" : "var(--text-muted)" }}>
        {children}
      </span>
    </div>
  );
}
