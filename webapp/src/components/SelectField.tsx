/**
 * SelectField — native <select> styled with IMEX AI tokens.
 *
 * Native <select> avoids custom-dropdown bundle weight (UI-SPEC §Registry Safety).
 * --surface fill, 1px --border, --r-md, 48px, muted placeholder, trailing chevron
 * (design-system §7 "Text input / select"). Colors via var(--token) only.
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

// Inline chevron (muted neutral; works on both themes) drawn as a background SVG.
const CHEVRON =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%238a93a6' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E\")";

const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(
  ({ id, options, placeholder, style, ...rest }, ref) => {
    return (
      <select
        id={id}
        ref={ref}
        style={{
          display: "block",
          width: "100%",
          minHeight: "48px", // touch target WCAG 2.5.5
          padding: "12px 38px 12px 12px",
          borderRadius: "var(--r-md)",
          backgroundColor: "var(--surface)",
          color: "var(--text)",
          border: "1px solid var(--border)",
          fontSize: "16px",
          fontFamily: "inherit",
          appearance: "none",
          backgroundImage: CHEVRON,
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 12px center",
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
