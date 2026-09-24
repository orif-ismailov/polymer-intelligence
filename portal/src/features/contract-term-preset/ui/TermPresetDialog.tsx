import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";

import { TemplateFieldInputs } from "@/entities/contract";
import type { TemplateField, TermPreset } from "@/entities/contract";
import { detailCode } from "@/shared/api";
import { Alert, Button, Dialog, FormField, Input } from "@/shared/ui";

import { useSaveTermPreset } from "../model/useSaveTermPreset";

interface TermPresetDialogProps {
  open: boolean;
  onClose: () => void;
  companyId: number;
  fields: TemplateField[];
  /** Editing this preset; absent means a new one. */
  preset?: TermPreset | null;
  /** Starting values for a new preset — «сохранить условия как шаблон». */
  initialTerms?: Record<string, string>;
  onSaved?: (preset: TermPreset) => void;
}

/**
 * Name a set of contract terms and save it for the company.
 *
 * The same dialog serves the presets page and the contract form's «сохранить
 * как шаблон», so a preset looks the same wherever it is made.
 */
export function TermPresetDialog({
  open,
  onClose,
  companyId,
  fields,
  preset,
  initialTerms,
  onSaved,
}: TermPresetDialogProps) {
  const { t } = useTranslation();
  const save = useSaveTermPreset(companyId);
  const [name, setName] = useState("");
  const [terms, setTerms] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(preset?.name ?? "");
    setTerms(preset?.terms ?? pick(initialTerms ?? {}, fields));
    setError(null);
  }, [open, preset, initialTerms, fields]);

  async function submit(): Promise<void> {
    setError(null);
    try {
      const saved = await save.mutateAsync({
        presetId: preset?.id ?? null,
        payload: { name: name.trim(), terms },
      });
      onSaved?.(saved);
      onClose();
    } catch (err) {
      const code = detailCode(err);
      setError(
        code === "preset_name_taken"
          ? t("contractTerms.errors.nameTaken")
          : t("contractTerms.errors.saveFailed"),
      );
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={preset ? t("contractTerms.edit") : t("contractTerms.new")}
      description={t("contractTerms.dialogHint")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!name.trim() || save.isPending}
            onClick={() => void submit()}
            data-testid="term-preset-save"
          >
            {save.isPending ? t("common.loading") : t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-4" data-testid="term-preset-dialog">
        <FormField label={t("contractTerms.name")} required>
          {({ id }) => (
            <Input
              id={id}
              value={name}
              maxLength={120}
              placeholder={t("contractTerms.namePlaceholder")}
              onChange={(e) => setName(e.target.value)}
              data-testid="term-preset-name"
            />
          )}
        </FormField>
        <TemplateFieldInputs
          fields={fields}
          values={terms}
          onChange={(key, value) =>
            setTerms((current) => ({ ...current, [key]: value }))
          }
        />
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
    </Dialog>
  );
}

function pick(
  values: Record<string, string>,
  fields: TemplateField[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    const value = values[f.key];
    if (value) out[f.key] = value;
  }
  return out;
}
