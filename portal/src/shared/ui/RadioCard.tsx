import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

import { IconTile } from "./IconTile";

interface RadioCardProps {
  /** Radio group name — all cards of one choice share it. */
  name: string;
  value: string;
  checked: boolean;
  onChange: (value: string) => void;
  title: string;
  description?: string;
  icon?: ReactNode;
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

/**
 * A full-width selectable card: glyph tile, title, two-line description, and the
 * radio dot pinned right (mockup sheet …39, «Выберите тип аккаунта»).
 *
 * The radio itself is a real `<input type="radio">` kept visually hidden but
 * focusable — arrow-key group navigation, screen-reader semantics and form
 * submission all come free, and the painted dot follows `peer-checked`. A
 * `<div role="radio">` would have had to re-implement all three.
 */
export function RadioCard({
  name,
  value,
  checked,
  onChange,
  title,
  description,
  icon,
  disabled,
  className,
  "data-testid": testId,
}: RadioCardProps) {
  return (
    <label
      className={cn(
        "group flex cursor-pointer items-center gap-3 rounded-md border bg-surface p-4 transition-colors",
        checked ? "border-brand bg-brand-soft/30" : "border-border hover:border-border-strong",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
      data-testid={testId}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="peer sr-only"
      />

      {icon ? (
        <IconTile tone={checked ? "brand" : "muted"}>{icon}</IconTile>
      ) : null}

      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-text">{title}</span>
        {description ? (
          <span className="mt-0.5 block text-xs leading-relaxed text-text-muted">{description}</span>
        ) : null}
      </span>

      {/* The painted dot. `peer-focus-visible` puts the focus ring here because
          the real input is off-screen — without it the card is keyboard-invisible. */}
      <span
        aria-hidden="true"
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-brand peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-surface",
          checked ? "border-brand" : "border-border-strong",
        )}
      >
        {checked ? <span className="h-2.5 w-2.5 rounded-full bg-brand shadow-glow" /> : null}
      </span>
    </label>
  );
}
