import { type DragEvent, useRef, useState } from "react";

import { cn } from "@/shared/lib";

import { UploadCloudIcon } from "./icons";

interface DropzoneProps {
  /** Primary line — «Перетащите файлы или нажмите для загрузки». */
  label: string;
  /** Second line — the accepted formats and size cap. */
  hint?: string;
  /** `accept` attribute of the underlying input. */
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  invalid?: boolean;
  onFiles: (files: File[]) => void;
  className?: string;
  "data-testid"?: string;
}

/**
 * The dashed drop target from the documents sheet: drag files onto it, or click
 * it to open the picker.
 *
 * A `<button>` wrapping a hidden `<input type="file">` rather than a styled
 * label, because the same element also has to answer drag events — and a label
 * that is both a drop target and a picker trigger fires the picker on drop in
 * Safari.
 */
export function Dropzone({
  label,
  hint,
  accept,
  multiple = false,
  disabled = false,
  invalid = false,
  onFiles,
  className,
  "data-testid": testId,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function emit(list: FileList | null): void {
    const files = Array.from(list ?? []);
    if (files.length > 0) onFiles(multiple ? files : files.slice(0, 1));
  }

  function handleDrop(e: DragEvent<HTMLButtonElement>): void {
    e.preventDefault();
    setOver(false);
    if (disabled) return;
    emit(e.dataTransfer.files);
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        onChange={(e) => {
          emit(e.target.files);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={handleDrop}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-1.5 rounded-md border border-dashed px-4 py-6 text-center transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 focus-visible:ring-offset-bg",
          "disabled:pointer-events-none disabled:opacity-60",
          over && "border-brand bg-brand-soft",
          !over && invalid && "border-danger",
          !over && !invalid && "border-border-strong hover:border-brand-line hover:bg-surface-2",
          className,
        )}
        data-testid={testId}
      >
        <span className={cn("text-text-subtle", over && "text-brand")}>
          <UploadCloudIcon size={22} />
        </span>
        <span className="text-sm font-medium text-text">{label}</span>
        {hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
      </button>
    </>
  );
}
