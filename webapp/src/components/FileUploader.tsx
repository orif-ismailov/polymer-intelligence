/**
 * FileUploader — file input + staged file list with client-side validation.
 *
 * Client-side validation (T-03-16 mitigation, UI-SPEC §File Upload):
 *   - Rejects > 5 files total
 *   - Rejects individual file > 10 MB
 *   - Rejects MIME not in {pdf, xlsx, xls, jpg, jpeg}
 * Validation runs in the change handler BEFORE staging (not on submit).
 *
 * Files are staged in wizardStore.files only; NOT uploaded here.
 * The remove × button fires notifyWarning() haptic.
 * aria-label="Удалить файл {name}" per UI-SPEC §Accessibility.
 */

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { notifyWarning } from "../telegram";
import { useWizardStore } from "../store/wizardStore";
import { X } from "lucide-react";

const ACCEPT_MIMES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", // xlsx
  "application/vnd.ms-excel", // xls
  "image/jpeg",
]);
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
const MAX_FILES = 5;

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} КБ`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function truncateName(name: string, max = 24): string {
  if (name.length <= max) return name;
  return `${name.slice(0, max - 1)}…`;
}

export default function FileUploader() {
  const { t } = useTranslation();
  const files = useWizardStore((s) => s.files);
  const setFiles = useWizardStore((s) => s.setFiles);
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    const selected = Array.from(e.target.files ?? []);
    if (!selected.length) return;

    // Total file count check
    if (files.length + selected.length > MAX_FILES) {
      setError(t("error.tooManyFiles"));
      // Reset input so the same file can be selected again after fixing
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    // Per-file validation
    for (const file of selected) {
      if (file.size > MAX_SIZE_BYTES) {
        setError(t("error.fileTooLarge"));
        if (inputRef.current) inputRef.current.value = "";
        return;
      }
      if (!ACCEPT_MIMES.has(file.type)) {
        setError(t("error.fileType"));
        if (inputRef.current) inputRef.current.value = "";
        return;
      }
    }

    setFiles([...files, ...selected]);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleRemove(index: number) {
    notifyWarning();
    setFiles(files.filter((_, i) => i !== index));
  }

  return (
    <div>
      {/* File staged list */}
      {files.length > 0 && (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: "0 0 12px",
          }}
        >
          {files.map((file, i) => (
            <li
              key={`${file.name}-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 12px",
                borderRadius: "8px",
                backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
                marginBottom: "6px",
              }}
            >
              <div style={{ overflow: "hidden" }}>
                <span
                  style={{
                    display: "block",
                    fontSize: "14px",
                    color: "var(--tg-theme-text-color, #f8fafc)",
                  }}
                >
                  {truncateName(file.name)}
                </span>
                <span
                  style={{
                    fontSize: "12px",
                    color: "var(--tg-theme-hint-color, #94a3b8)",
                  }}
                >
                  {formatFileSize(file.size)}
                </span>
              </div>
              <button
                type="button"
                aria-label={t("fileUploader.remove", { name: file.name })}
                onClick={() => handleRemove(i)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minWidth: "44px",
                  minHeight: "44px",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--tg-theme-hint-color, #94a3b8)",
                  padding: "8px",
                  flexShrink: 0,
                }}
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Attach button — visible when under limit */}
      {files.length < MAX_FILES && (
        <label
          htmlFor="file-uploader-input"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "44px",
            padding: "10px 16px",
            borderRadius: "8px",
            border: "1.5px dashed var(--tg-theme-hint-color, #94a3b8)",
            cursor: "pointer",
            fontSize: "14px",
            color: "var(--tg-theme-hint-color, #94a3b8)",
            gap: "8px",
          }}
        >
          {t("fileUploader.attach")}
          <input
            id="file-uploader-input"
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.xlsx,.xls,.jpg,.jpeg"
            onChange={handleChange}
            style={{ display: "none" }}
          />
        </label>
      )}

      <p
        style={{
          fontSize: "12px",
          color: "var(--tg-theme-hint-color, #94a3b8)",
          margin: "6px 0 0",
        }}
      >
        {t("fileUploader.hint")}
      </p>

      {/* Inline validation error */}
      {error && (
        <span
          role="alert"
          style={{
            display: "block",
            fontSize: "13px",
            color: "#ef4444",
            marginTop: "6px",
          }}
        >
          {error}
        </span>
      )}
    </div>
  );
}
