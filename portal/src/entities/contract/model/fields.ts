import type { ContractTemplate } from "./types";

/** One form field, read off a template's `variables_schema`. */
export interface TemplateField {
  key: string;
  title: string;
  enum?: string[];
  required: boolean;
}

/**
 * The variables a company may save as «шаблон условий» — its terms, never the
 * deal's own numbers. Mirrors `term_presets.PRESET_KEYS` on the server, which
 * refuses anything else.
 */
export const PRESET_KEYS: ReadonlySet<string> = new Set([
  "currency",
  "unit",
  "incoterms",
  "payment_terms",
  "delivery_window",
  "special_conditions",
]);

export function templateFields(template: ContractTemplate): TemplateField[] {
  const schema = template.variables_schema as {
    properties?: Record<string, { title?: string; enum?: string[] }>;
    required?: string[];
  };
  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  return Object.entries(props).map(([key, spec]) => ({
    key,
    title: spec.title ?? key,
    enum: spec.enum,
    required: required.has(key),
  }));
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
