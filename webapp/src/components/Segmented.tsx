/**
 * Segmented control — token-themed, wraps to multiple rows when there are many
 * options (e.g. the four language choices). Active segment uses the green accent.
 */

import type { CSSProperties } from "react";

export interface SegOption<T extends string> {
  value: T;
  label: string;
}

interface SegmentedProps<T extends string> {
  value: T;
  options: SegOption<T>[];
  onChange: (value: T) => void;
  ariaLabel?: string;
}

export default function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: SegmentedProps<T>) {
  const base: CSSProperties = {
    flex: "1 0 auto",
    minWidth: "72px",
    minHeight: "44px",
    padding: "10px 12px",
    border: "none",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    boxSizing: "border-box",
    background: "transparent",
    color: "var(--text-muted)",
  };
  const active: CSSProperties = {
    ...base,
    background: "var(--green)",
    color: "var(--green-on)",
  };

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      style={{
        display: "flex",
        flexWrap: "wrap",
        borderRadius: "var(--r-md)",
        overflow: "hidden",
        border: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          style={value === o.value ? active : base}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
