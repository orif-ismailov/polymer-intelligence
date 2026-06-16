/**
 * FieldGroup — label + input/select/textarea + inline zod error.
 *
 * Typography: label at 13px/400 hint color; error at 13px #ef4444.
 * Accessibility: label.htmlFor wired to input id; error referenced via aria-describedby.
 */

import { ReactNode } from "react";

interface FieldGroupProps {
  /** Matches the id of the child input/select/textarea. */
  htmlFor: string;
  label: string;
  /** The error message string (from react-hook-form fieldState.error.message). */
  error?: string;
  children: ReactNode;
}

export default function FieldGroup({ htmlFor, label, error, children }: FieldGroupProps) {
  const errorId = error ? `${htmlFor}-error` : undefined;

  return (
    <div style={{ marginBottom: "16px" }}>
      <label
        htmlFor={htmlFor}
        style={{
          display: "block",
          fontSize: "13px",
          fontWeight: 400,
          color: "var(--tg-theme-hint-color, #94a3b8)",
          marginBottom: "4px",
        }}
      >
        {label}
      </label>

      {/* Clone children with aria-describedby pointing at the error span */}
      <div
        aria-describedby={errorId}
      >
        {children}
      </div>

      {error && (
        <span
          id={errorId}
          role="alert"
          style={{
            display: "block",
            fontSize: "13px",
            color: "#ef4444",
            marginTop: "4px",
          }}
        >
          {error}
        </span>
      )}
    </div>
  );
}
