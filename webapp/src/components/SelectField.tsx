/**
 * SelectField — native <select> styled with tg-theme vars.
 *
 * Uses native <select> to avoid custom dropdown bundle weight (UI-SPEC §Registry Safety).
 * All colors via var(--tg-theme-*); no hardcoded hex.
 */

import { SelectHTMLAttributes, forwardRef } from "react";

interface Option {
  value: string | number;
  label: string;
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  id: string;
  options: Option[];
  placeholder?: string;
}

const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(
  ({ id, options, placeholder, style, ...rest }, ref) => {
    return (
      <select
        id={id}
        ref={ref}
        style={{
          display: "block",
          width: "100%",
          minHeight: "44px", // touch target WCAG 2.5.5
          padding: "10px 12px",
          borderRadius: "8px",
          backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
          color: "var(--tg-theme-text-color, #f8fafc)",
          border: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
          fontSize: "14px",
          fontFamily: "system-ui, sans-serif",
          appearance: "none",
          boxSizing: "border-box",
          ...style,
        }}
        {...rest}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    );
  },
);

SelectField.displayName = "SelectField";

export default SelectField;
