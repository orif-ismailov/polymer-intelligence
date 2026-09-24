import type { ContractTemplate } from "./types";

/** How a text field is typed — `x-input` in the schema. */
export type FieldInput = "text" | "number" | "multiline" | "date";

/** One form field, read off a template's `variables_schema`. */
export interface TemplateField {
  key: string;
  title: string;
  enum?: string[];
  /** `x-enum-labels`: what each allowed value reads as on the form. */
  labels?: Record<string, string>;
  required: boolean;
  /** `x-group`: which card of the form the field sits in. */
  group: string | null;
  /** `x-when`: shown only while another field holds one of these values. */
  when: Record<string, string[]> | null;
  /** `x-hidden`: fixed by the template (the contract kind), never shown. */
  hidden: boolean;
  default?: string;
  input: FieldInput;
}

/**
 * The variables a company may save as «шаблон условий» — its terms and switches,
 * never the deal's own numbers or its parties. Mirrors `term_presets.PRESET_KEYS`
 * on the server, which refuses anything else.
 */
export const PRESET_KEYS: ReadonlySet<string> = new Set([
  "currency",
  "unit",
  "incoterms",
  "payment_terms",
  "delivery_window",
  "special_conditions",
  "vat_rate",
  "payment_mode",
  "refuse_after_days",
  "delivery_days",
  "delivery_basis",
  "pickup_days",
  "delivery_address",
  "delivery_note",
  "packaging",
  "quality_section",
  "penalty_delivery_pct",
  "penalty_delivery_cap",
  "penalty_payment_pct",
  "penalty_payment_cap",
  "refusal_fine_pct",
]);

interface SchemaProperty {
  title?: string;
  enum?: string[];
  default?: string;
  "x-enum-labels"?: Record<string, string>;
  "x-group"?: string;
  "x-when"?: Record<string, string>;
  "x-hidden"?: boolean;
  "x-input"?: FieldInput;
}

export function templateFields(template: ContractTemplate): TemplateField[] {
  const schema = template.variables_schema as {
    properties?: Record<string, SchemaProperty>;
    required?: string[];
    "x-order"?: string[];
  };
  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  // Postgres JSONB keeps no key order; a template that cares says so.
  const order = schema["x-order"] ?? [];
  const rank = (key: string) => {
    const i = order.indexOf(key);
    return i === -1 ? order.length : i;
  };
  const entries = Object.entries(props).sort(([a], [b]) => rank(a) - rank(b));
  return entries.map(([key, spec]) => {
    const when = spec["x-when"];
    return {
      key,
      title: spec.title ?? key,
      enum: spec.enum,
      labels: spec["x-enum-labels"],
      required: required.has(key),
      group: spec["x-group"] ?? null,
      // `a|b` means either value shows the field.
      when: when
        ? Object.fromEntries(
            Object.entries(when).map(([k, v]) => [k, v.split("|")]),
          )
        : null,
      hidden: spec["x-hidden"] === true,
      default: spec.default,
      input: spec["x-input"] ?? "text",
    };
  });
}

/** Whether a field applies, given the values the form holds right now. */
export function isFieldVisible(
  field: TemplateField,
  values: Record<string, string>,
): boolean {
  if (field.hidden) return false;
  if (!field.when) return true;
  return Object.entries(field.when).every(([key, allowed]) =>
    allowed.includes(values[key] ?? ""),
  );
}

/** The template's own starting values: its defaults. */
export function templateDefaults(
  fields: TemplateField[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) if (f.default != null) out[f.key] = f.default;
  return out;
}

/** The fields a preset covers, as the template spells them. */
export function presetFields(template: ContractTemplate): TemplateField[] {
  return templateFields(template)
    .filter((f) => PRESET_KEYS.has(f.key))
    .map((f) => ({ ...f, required: false }));
}

/**
 * Preset fields across every active template — the first template to declare a
 * key names it. A preset is not tied to one template, and the templates share
 * these keys, so this is the one form a preset is edited in.
 */
export function presetFieldsOf(
  templates: readonly ContractTemplate[],
): TemplateField[] {
  const seen = new Map<string, TemplateField>();
  for (const template of templates) {
    for (const f of presetFields(template))
      if (!seen.has(f.key)) seen.set(f.key, f);
  }
  return [...seen.values()];
}
