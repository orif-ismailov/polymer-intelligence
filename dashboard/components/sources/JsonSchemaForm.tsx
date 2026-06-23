"use client";

/**
 * JsonSchemaForm — auto-renders form fields from a Pydantic v2 JSON Schema.
 *
 * Supports:
 * - string / url (SSRF hint "Public URLs only.")
 * - integer / number → number input
 * - enum → shadcn Select
 * - boolean → checkbox
 * - anyOf:[T, null] (Pydantic Optional fields) → unwrapped to T (RESEARCH Pitfall 4)
 * - required[] mirrored client-side for * label
 *
 * No hardcoded hex — all colors via Tailwind token classes.
 */

import { useState } from "react";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface RawSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  format?: string;
  enum?: string[];
  default?: unknown;
  anyOf?: Array<{ type?: string; format?: string; enum?: string[] }>;
  items?: RawSchemaProperty;
}

interface ConfigSchema {
  properties?: Record<string, RawSchemaProperty>;
  required?: string[];
  title?: string;
}

export interface JsonSchemaFormValues {
  [key: string]: string | number | boolean | null;
}

interface JsonSchemaFormProps {
  schema: ConfigSchema;
  initialValues?: JsonSchemaFormValues;
  onSubmit: (values: JsonSchemaFormValues) => void;
  submitLabel?: string;
  onBack?: () => void;
  backLabel?: string;
}

// ─── anyOf unwrapper (RESEARCH Pitfall 4) ────────────────────────────────────

/**
 * Pydantic v2 Optional[X] → anyOf:[X, {type:"null"}]
 * Unwrap to X so the form renderer sees a plain schema property.
 */
function resolveType(prop: RawSchemaProperty): RawSchemaProperty {
  if (prop.anyOf && Array.isArray(prop.anyOf)) {
    const nonNull = prop.anyOf.find((s) => s.type !== "null");
    if (nonNull) {
      return { ...prop, ...nonNull, anyOf: undefined };
    }
  }
  return prop;
}

// ─── Field subcomponents ──────────────────────────────────────────────────────

interface FieldWrapperProps {
  label: string;
  name: string;
  required: boolean;
  hint?: string;
  children: React.ReactNode;
}

function FieldWrapper({ label, name, required, hint, children }: FieldWrapperProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={name} className="text-xs font-semibold text-foreground-muted">
        {label}
        {required && <span className="ml-0.5 text-urgency-high" aria-label="required">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-foreground-subtle">{hint}</p>}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function JsonSchemaForm({
  schema,
  initialValues = {},
  onSubmit,
  submitLabel = "Continue",
  onBack,
  backLabel = "Back",
}: JsonSchemaFormProps) {
  const properties = schema.properties ?? {};
  const requiredSet = new Set(schema.required ?? []);

  // Initialize form state from initialValues + schema defaults
  const [values, setValues] = useState<JsonSchemaFormValues>(() => {
    const init: JsonSchemaFormValues = {};
    for (const [key, rawProp] of Object.entries(properties)) {
      const prop = resolveType(rawProp);
      if (key in initialValues) {
        init[key] = initialValues[key]!;
      } else if (prop.default !== undefined) {
        init[key] = prop.default as string | number | boolean | null;
      } else if (prop.type === "boolean") {
        init[key] = false;
      } else {
        init[key] = "";
      }
    }
    return init;
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  function setValue(key: string, val: string | number | boolean | null) {
    setValues((prev) => ({ ...prev, [key]: val }));
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  }

  function validate(): boolean {
    const newErrors: Record<string, string> = {};
    for (const key of requiredSet) {
      const val = values[key];
      if (val === "" || val === null || val === undefined) {
        const rawProp = properties[key];
        const label = rawProp?.title ?? key;
        newErrors[key] = `${label} is required`;
      }
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (validate()) {
      onSubmit(values);
    }
  }

  const entries = Object.entries(properties);
  if (entries.length === 0) {
    return (
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-sm text-foreground-muted">
          No configuration required for this source type.
        </p>
        <div className="flex gap-3 justify-end">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="rounded-md border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary transition-colors"
            >
              {backLabel}
            </button>
          )}
          <button
            type="submit"
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark transition-colors"
          >
            {submitLabel}
          </button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {entries.map(([key, rawProp]) => {
        const prop = resolveType(rawProp);
        const isRequired = requiredSet.has(key);
        const label = prop.title ?? key;
        const fieldId = `jsf-${key}`;
        const errorMsg = errors[key];

        // URL field — SSRF hint
        if (prop.format === "uri") {
          return (
            <FieldWrapper key={key} label={label} name={fieldId} required={isRequired} hint="Public URLs only.">
              <input
                id={fieldId}
                name={key}
                type="url"
                value={(values[key] as string) ?? ""}
                onChange={(e) => setValue(key, e.target.value)}
                required={isRequired}
                placeholder="https://example.com/data"
                className={`rounded-md border ${errorMsg ? "border-urgency-high" : "border-border"} bg-background-tertiary px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary`}
              />
              {errorMsg && <p className="text-xs text-urgency-high">{errorMsg}</p>}
            </FieldWrapper>
          );
        }

        // Enum → Select
        if (prop.enum && prop.enum.length > 0) {
          return (
            <FieldWrapper key={key} label={label} name={fieldId} required={isRequired} hint={prop.description}>
              <select
                id={fieldId}
                name={key}
                value={(values[key] as string) ?? ""}
                onChange={(e) => setValue(key, e.target.value)}
                required={isRequired}
                className={`rounded-md border ${errorMsg ? "border-urgency-high" : "border-border"} bg-background-tertiary px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary`}
              >
                <option value="">Select {label}…</option>
                {prop.enum.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
              {errorMsg && <p className="text-xs text-urgency-high">{errorMsg}</p>}
            </FieldWrapper>
          );
        }

        // Integer / Number → number input
        if (prop.type === "integer" || prop.type === "number") {
          return (
            <FieldWrapper key={key} label={label} name={fieldId} required={isRequired} hint={prop.description}>
              <input
                id={fieldId}
                name={key}
                type="number"
                step={prop.type === "integer" ? "1" : "any"}
                value={(values[key] as number) ?? ""}
                onChange={(e) => setValue(key, e.target.value === "" ? "" : Number(e.target.value))}
                required={isRequired}
                className={`rounded-md border ${errorMsg ? "border-urgency-high" : "border-border"} bg-background-tertiary px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary`}
              />
              {errorMsg && <p className="text-xs text-urgency-high">{errorMsg}</p>}
            </FieldWrapper>
          );
        }

        // Boolean → checkbox
        if (prop.type === "boolean") {
          return (
            <div key={key} className="flex items-center gap-2">
              <input
                id={fieldId}
                name={key}
                type="checkbox"
                checked={(values[key] as boolean) ?? false}
                onChange={(e) => setValue(key, e.target.checked)}
                className="h-4 w-4 rounded border-border bg-background-tertiary text-accent focus:ring-accent"
              />
              <label htmlFor={fieldId} className="text-sm text-foreground">
                {label}
                {isRequired && <span className="ml-0.5 text-urgency-high" aria-label="required">*</span>}
              </label>
            </div>
          );
        }

        // Default: text input
        return (
          <FieldWrapper key={key} label={label} name={fieldId} required={isRequired} hint={prop.description}>
            <input
              id={fieldId}
              name={key}
              type="text"
              value={(values[key] as string) ?? ""}
              onChange={(e) => setValue(key, e.target.value)}
              required={isRequired}
              placeholder={prop.description ?? `Enter ${label}…`}
              className={`rounded-md border ${errorMsg ? "border-urgency-high" : "border-border"} bg-background-tertiary px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary`}
            />
            {errorMsg && <p className="text-xs text-urgency-high">{errorMsg}</p>}
          </FieldWrapper>
        );
      })}

      <div className="flex gap-3 justify-end pt-2">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="rounded-md border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary transition-colors"
          >
            {backLabel}
          </button>
        )}
        <button
          type="submit"
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background-secondary"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
