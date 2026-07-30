import { type ChangeEvent, useId, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from "@/shared/config";
import { useEnumLabels } from "@/shared/i18n";
import { formatBytes } from "@/shared/lib";
import { cn } from "@/shared/lib";
import { Badge, FileIcon, Spinner } from "@/shared/ui";

const ACCEPT = "application/pdf,image/jpeg,image/png";

/**
 * The same set as ACCEPT, but enforced in JS as well.
 *
 * `accept` only filters the OS file dialog — it is a hint, not a gate, and a user
 * who picks "All files" (or drags one in) sails straight past it. Without this
 * check an unsupported file was accepted into the form and rejected only by the
 * server at the END of the wizard, after the company, profile, roles and bank
 * account had already been written. The server still checks magic bytes and
 * remains the authority; this just moves the obvious "no" to where the user is.
 */
const ALLOWED_TYPES = new Set(["application/pdf", "image/jpeg", "image/png"]);
/** Fallback for browsers/files that report an empty `type`. */
const ALLOWED_EXTENSIONS = /\.(pdf|jpe?g|png)$/i;

function isAllowedFile(file: File): boolean {
  if (file.type) return ALLOWED_TYPES.has(file.type);
  return ALLOWED_EXTENSIONS.test(file.name);
}

export interface SelectedDocument {
  kind: string;
  file: File;
}

interface DocumentDropzoneProps {
  kind: string;
  required?: boolean;
  /** Currently-selected file for this kind, if any. */
  file: File | null;
  uploading?: boolean;
  onSelect: (file: File) => void;
  onClear: () => void;
}

/**
 * Single-kind document picker. Validates size client-side and surfaces the
 * chosen file with a replace/remove affordance. Actual upload is orchestrated
 * by the caller (wizard confirm step / company view).
 */
export function DocumentDropzone({
  kind,
  required,
  file,
  uploading,
  onSelect,
  onClear,
}: DocumentDropzoneProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [error, setError] = useState<string | null>(null);

  function handleChange(e: ChangeEvent<HTMLInputElement>): void {
    const chosen = e.target.files?.[0];
    e.target.value = "";
    if (!chosen) return;
    if (chosen.size > MAX_UPLOAD_BYTES) {
      setError(t("wizard.documents.tooLarge", { mb: MAX_UPLOAD_MB }));
      return;
    }
    if (!isAllowedFile(chosen)) {
      setError(t("wizard.documents.invalidType"));
      return;
    }
    setError(null);
    onSelect(chosen);
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-sm font-medium text-text">{label("documentKind", kind)}</span>
        {required ? (
          <Badge tone="warning">{t("common.required")}</Badge>
        ) : (
          <Badge tone="neutral">{t("common.optional")}</Badge>
        )}
      </div>

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={handleChange}
      />

      {file ? (
        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            {uploading ? <Spinner /> : <FileIcon size={16} className="shrink-0 text-text-subtle" />}
            <div className="min-w-0">
              <p className="truncate text-sm text-text">{file.name}</p>
              <p className="text-xs text-text-muted">{formatBytes(file.size)}</p>
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="text-xs font-medium text-brand hover:underline disabled:opacity-60"
            >
              {t("wizard.documents.replace")}
            </button>
            <button
              type="button"
              onClick={onClear}
              disabled={uploading}
              className="text-xs font-medium text-danger hover:underline disabled:opacity-60"
            >
              {t("common.remove")}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className={cn(
            "flex w-full flex-col items-center justify-center gap-1 rounded-md border border-dashed px-3 py-6 text-center transition-colors hover:bg-surface-2",
            error ? "border-danger" : "border-border-strong",
          )}
        >
          <span className="text-sm font-medium text-text">{t("company.uploadDocument")}</span>
          <span className="text-xs text-text-muted">
            {t("wizard.documents.dropHint", { mb: MAX_UPLOAD_MB })}
          </span>
        </button>
      )}

      {error ? (
        <p role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
