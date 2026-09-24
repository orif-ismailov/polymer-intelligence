import { FormField, Input, Select } from "@/shared/ui";

import type { TemplateField } from "../model/fields";

interface TemplateFieldInputsProps {
  fields: TemplateField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}

/**
 * One input per template variable: a Select where the schema names the allowed
 * values, a text field otherwise. Shared by the contract form and the «шаблон
 * условий» editor, so a preset is typed into exactly the controls it later fills.
 */
export function TemplateFieldInputs({
  fields,
  values,
  onChange,
}: TemplateFieldInputsProps) {
  return (
    <>
      {fields.map((f) => (
        <FormField key={f.key} label={f.title} required={f.required}>
          {({ id }) =>
            f.enum ? (
              <Select
                id={id}
                value={values[f.key] ?? ""}
                onChange={(e) => onChange(f.key, e.target.value)}
                options={[
                  { value: "", label: "—" },
                  ...f.enum.map((o) => ({ value: o, label: o })),
                ]}
                data-testid={`field-${f.key}`}
              />
            ) : (
              <Input
                id={id}
                value={values[f.key] ?? ""}
                onChange={(e) => onChange(f.key, e.target.value)}
                data-testid={`field-${f.key}`}
              />
            )
          }
        </FormField>
      ))}
    </>
  );
}
