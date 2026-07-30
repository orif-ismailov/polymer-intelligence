import { forwardRef, useRef, type InputHTMLAttributes } from "react";

import { Input } from "./Input";
import { CalendarIcon } from "./icons";

export interface DateInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "children"> {
  invalid?: boolean;
  /** Accessible name for the picker button — the caller supplies the string. */
  pickerLabel?: string;
}

/**
 * `<input type="date">` wearing the mockups' calendar glyph.
 *
 * The UA draws its own picker indicator, so a design-system glyph on top gives
 * the field two calendars — this hides the native one (`.date-field` in
 * styles.css) and wires ours to `showPicker()`, keeping one affordance that
 * still opens the platform picker.
 */
export const DateInput = forwardRef<HTMLInputElement, DateInputProps>(function DateInput(
  { className, pickerLabel, ...rest },
  ref,
) {
  const local = useRef<HTMLInputElement | null>(null);

  return (
    <Input
      ref={(node) => {
        local.current = node;
        if (typeof ref === "function") ref(node);
        else if (ref) ref.current = node;
      }}
      type="date"
      className={className ? `date-field ${className}` : "date-field"}
      trailing={
        <button
          type="button"
          aria-label={pickerLabel}
          onClick={() => {
            const node = local.current;
            if (!node) return;
            // `showPicker` is Chromium/WebKit-only; Firefox falls back to focus.
            if (typeof node.showPicker === "function") node.showPicker();
            else node.focus();
          }}
          className="rounded-sm text-brand transition-colors hover:brightness-125 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <CalendarIcon size={18} />
        </button>
      }
      {...rest}
    />
  );
});
