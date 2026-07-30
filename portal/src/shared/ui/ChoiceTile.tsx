import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

export type ChoiceTileTone = "brand" | "gold";

interface ChoiceTileProps {
  /** Radio group name — all tiles of one choice share it. */
  name: string;
  value: string;
  checked: boolean;
  onChange: (value: string) => void;
  title: string;
  description?: string;
  icon?: ReactNode;
  /**
   * Colour of the chosen state. The add-product sheets use `gold` for
   * «Тип предложения» and `brand` for «Лабораторный паспорт» — a deliberate
   * distinction, so it is a prop rather than a constant.
   */
  tone?: ChoiceTileTone;
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

const selectedTones: Record<ChoiceTileTone, string> = {
  brand: "border-brand bg-brand-soft text-text",
  gold: "border-gold bg-gold-soft text-text",
};

const glyphTones: Record<ChoiceTileTone, string> = {
  brand: "text-brand",
  gold: "text-gold",
};

/**
 * A square, stacked selectable tile: glyph on top, title, caption under it —
 * the two-up choices on the add-product sheets («В наличии / Под заказ»,
 * «У меня есть паспорт / Нет паспорта»).
 *
 * Distinct from {@link RadioCard}, which is the wide row with the dot pinned
 * right. This one has no dot at all: the tile itself is the indicator, which is
 * why the selected state carries both a border AND a wash — colour alone would
 * be the only signal.
 *
 * The control underneath is a real `<input type="radio">`, hidden but focusable,
 * so arrow-key navigation and screen-reader grouping come for free.
 */
export function ChoiceTile({
  name,
  value,
  checked,
  onChange,
  title,
  description,
  icon,
  tone = "brand",
  disabled,
  className,
  "data-testid": testId,
}: ChoiceTileProps) {
  return (
    <label
      className={cn(
        "group relative flex cursor-pointer flex-col items-center gap-1.5 rounded-md border px-3 py-4 text-center transition-colors",
        "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-bg",
        checked ? selectedTones[tone] : "border-border bg-surface-inset hover:border-border-strong",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
      data-testid={testId}
      data-checked={checked || undefined}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="sr-only"
      />
      {icon ? (
        <span className={cn("shrink-0", checked ? glyphTones[tone] : "text-text-muted")}>
          {icon}
        </span>
      ) : null}
      <span className="text-sm font-semibold">{title}</span>
      {description ? (
        <span className="text-xs leading-snug text-text-muted">{description}</span>
      ) : null}
    </label>
  );
}
