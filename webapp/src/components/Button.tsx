/**
 * Button — the one button implementation for the Mini App (design-system §7).
 *
 * Full-width, 48px tall, --r-md, 16/600. Variants map to the documented accent
 * semantics:
 *   - primary   → --green fill (global primary CTA: "Далее", "Купить сырьё", "Отправить заявку")
 *   - seller    → --orange fill (seller-wizard primary: "Опубликовать предложение")
 *   - telegram  → --blue fill ("Написать в Telegram", "Открыть чат")
 *   - secondary → --surface fill + --border ("Мои заявки", "На главную")
 * Disabled → neutral chip fill + muted text.
 */

import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

type Variant = "primary" | "seller" | "telegram" | "secondary";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const FILLS: Record<Exclude<Variant, "secondary">, { bg: string; fg: string }> = {
  primary: { bg: "var(--green)", fg: "var(--green-on)" },
  seller: { bg: "var(--orange)", fg: "#ffffff" },
  telegram: { bg: "var(--blue)", fg: "#ffffff" },
};

export default function Button({ variant = "primary", disabled, style, children, ...rest }: ButtonProps) {
  const base: CSSProperties = {
    display: "block",
    width: "100%",
    minHeight: "48px",
    padding: "12px 20px",
    borderRadius: "var(--r-md)",
    border: "none",
    fontSize: "16px",
    fontWeight: 600,
    cursor: disabled ? "not-allowed" : "pointer",
    boxSizing: "border-box",
  };

  let skin: CSSProperties;
  if (disabled) {
    skin = { background: "var(--chip-neutral-bg)", color: "var(--text-muted)" };
  } else if (variant === "secondary") {
    skin = { background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)" };
  } else {
    const f = FILLS[variant];
    skin = { background: f.bg, color: f.fg };
  }

  return (
    <button type="button" disabled={disabled} style={{ ...base, ...skin, ...style }} {...rest}>
      {children}
    </button>
  );
}
