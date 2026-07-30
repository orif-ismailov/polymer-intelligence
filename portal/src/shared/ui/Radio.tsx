import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  description?: string;
}

/**
 * A plain labelled radio row — «Бесплатно / Платно», «Способ продажи» on the
 * sales-terms sheet.
 *
 * The lightweight sibling of {@link RadioCard} (glyph tile + description +
 * painted dot) and of {@link ChoiceTile} (stacked square). The mockups use all
 * three, and picking the wrong one is what makes a rebuilt screen read as
 * "close but not it": these rows are a compact list, not a set of cards.
 *
 * Mirrors {@link Checkbox} down to the `accent-*` trick, so a checkbox row and a
 * radio row in the same sheet are the same object with a different mark.
 */
export const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { label, description, className, id, ...rest },
  ref,
) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-md border border-border bg-surface px-3 py-2.5 transition-colors hover:bg-surface-2 has-[:checked]:border-brand-line has-[:checked]:bg-brand-soft",
        className,
      )}
    >
      <input
        ref={ref}
        id={id}
        type="radio"
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--brand)]"
        {...rest}
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-text">{label}</span>
        {description ? (
          <span className="mt-0.5 block text-xs text-text-muted">{description}</span>
        ) : null}
      </span>
    </label>
  );
});
