import { useTranslation } from "react-i18next";

import { FormField, Input, Segmented, Select, Textarea } from "@/shared/ui";

import { isFieldVisible, type TemplateField } from "../model/fields";

interface TemplateFieldInputsProps {
  fields: TemplateField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}

/** Up to this many choices read best as a switch; more become a dropdown. */
const SWITCH_MAX = 3;

/**
 * The template's fields, as a form: grouped by `x-group`, each shown only while
 * its `x-when` holds, a switch for a short choice and a dropdown for a long one.
 *
 * Shared by the contract form and the «шаблон условий» editor, so a preset is
 * typed into exactly the controls it later fills.
 */
export function TemplateFieldInputs({
  fields,
  values,
  onChange,
}: TemplateFieldInputsProps) {
  const { t } = useTranslation();
  const visible = fields.filter((f) => isFieldVisible(f, values));
  const groups: { id: string | null; fields: TemplateField[] }[] = [];
  for (const field of visible) {
    const existing = groups.find((g) => g.id === field.group);
    if (existing) existing.fields.push(field);
    else groups.push({ id: field.group, fields: [field] });
  }

  return (
    <>
      {groups.map((group) => (
        <fieldset
          key={group.id ?? "_"}
          className="space-y-4"
          data-testid={`fields-${group.id ?? "main"}`}
        >
          {group.id ? (
            <legend className="mb-1 text-sm font-semibold text-text">
              {t(`contracts.groups.${group.id}`, { defaultValue: group.id })}
            </legend>
          ) : null}
          {group.fields.map((f) => (
            <FormField key={f.key} label={f.title} required={f.required}>
              {({ id }) => (
                <FieldControl
                  id={id}
                  field={f}
                  value={values[f.key] ?? ""}
                  onChange={onChange}
                />
              )}
            </FormField>
          ))}
        </fieldset>
      ))}
    </>
  );
}

function FieldControl({
  id,
  field,
  value,
  onChange,
}: {
  id: string;
  field: TemplateField;
  value: string;
  onChange: (key: string, value: string) => void;
}) {
  const testId = `field-${field.key}`;
  if (field.enum) {
    const options = field.enum.map((o) => ({
      value: o,
      label: field.labels?.[o] ?? o,
    }));
    if (field.labels && options.length <= SWITCH_MAX) {
      return (
        <Segmented
          options={options}
          value={value}
          onChange={(next) => onChange(field.key, next)}
          ariaLabel={field.title}
          data-testid={testId}
        />
      );
    }
    return (
      <Select
        id={id}
        value={value}
        onChange={(e) => onChange(field.key, e.target.value)}
        options={[{ value: "", label: "—" }, ...options]}
        data-testid={testId}
      />
    );
  }
  if (field.input === "multiline") {
    return (
      <Textarea
        id={id}
        rows={3}
        value={value}
        onChange={(e) => onChange(field.key, e.target.value)}
        data-testid={testId}
      />
    );
  }
  return (
    <Input
      id={id}
      inputMode={field.input === "number" ? "decimal" : undefined}
      value={value}
      onChange={(e) => onChange(field.key, e.target.value)}
      data-testid={testId}
    />
  );
}
