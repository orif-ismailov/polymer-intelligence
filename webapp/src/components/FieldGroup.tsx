/**
 * FieldGroup — label + input/select/textarea + inline zod error.
 *
 * Typography (design-system §5): label 13/500 --text-muted; a trailing red `*`
 * when `required`; error 13px --danger.
 * Accessibility: label.htmlFor wired to input id; error referenced via aria-describedby.
 */

import { ReactNode } from "react";

interface FieldGroupProps {
  /** Matches the id of the child input/select/textarea. */
  htmlFor: string;
  label: string;
  /** Append a red `*` to the label (design-system §5). */
  required?: boolean;
  /** The error message string (from react-hook-form fieldState.error.message). */
  error?: string;
  children: ReactNode;
}

export default function FieldGroup({ htmlFor, label, required, error, children }: FieldGroupProps) {
  const errorId = error ? `${htmlFor}-error` : undefined;

  return (
    <div style={{ marginBottom: "16px" }}>
      <label
        htmlFor={htmlFor}
        style={{
          display: "block",
          fontSize: "13px",
          fontWeight: 500,
          color: "var(--text-muted)",
          marginBottom: "6px",
        }}
      >
        {label}
        {required && <span style={{ color: "var(--danger)", marginLeft: "2px" }}>*</span>}
      </label>

      {/* Clone children with aria-describedby pointing at the error span */}
      <div aria-describedby={errorId}>{children}</div>

      {error && (
        <span
          id={errorId}
          role="alert"
          style={{
            display: "block",
            fontSize: "13px",
            color: "var(--danger)",
            marginTop: "4px",
          }}
        >
          {error}
        </span>
      )}
    </div>
  );
}
