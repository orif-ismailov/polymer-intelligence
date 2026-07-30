import { type KeyboardEvent, useState } from "react";

import { cn } from "@/shared/lib";

import { CloseIcon, PlusIcon } from "./icons";
import { Input } from "./Input";

interface ChipInputProps {
  values: readonly string[];
  onChange: (values: string[]) => void;
  id?: string;
  placeholder?: string;
  /** Label for the ✕ on each pill, e.g. «Удалить». */
  removeLabel: string;
  /** Label for the add button. */
  addLabel: string;
  max?: number;
  disabled?: boolean;
  className?: string;
  "data-testid"?: string;
}

/**
 * Free-text pills — «Ключевые свойства» and «Применение» on the extra-info
 * sheet, where each value renders as its own chip.
 *
 * Enter commits (a chip is a phrase, so a lone Enter in a one-line field has no
 * other job), and so does the explicit ＋ next to it: keyboard-only commit is a
 * pattern people miss, and these two fields are the last thing between a seller
 * and publishing.
 *
 * Duplicates are dropped silently rather than flagged — a repeated chip is a
 * slip, not an error worth a message.
 */
export function ChipInput({
  values,
  onChange,
  id,
  placeholder,
  removeLabel,
  addLabel,
  max = 12,
  disabled = false,
  className,
  "data-testid": testId,
}: ChipInputProps) {
  const [draft, setDraft] = useState("");
  const full = values.length >= max;

  function commit(): void {
    const value = draft.trim();
    setDraft("");
    if (value === "" || full || values.includes(value)) return;
    onChange([...values, value]);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
      return;
    }
    // Backspace on an empty field pops the last chip — the standard token-field
    // gesture, and the only way to undo a typo without reaching for the mouse.
    if (e.key === "Backspace" && draft === "" && values.length > 0) {
      onChange(values.slice(0, -1));
    }
  }

  return (
    <div className={cn("space-y-2", className)} data-testid={testId}>
      {values.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {values.map((value) => (
            <li key={value}>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-2 py-1 pe-1.5 ps-3 text-xs font-medium text-text">
                {value}
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={`${removeLabel}: ${value}`}
                  onClick={() => onChange(values.filter((v) => v !== value))}
                  className="rounded-full p-0.5 text-text-subtle transition-colors hover:bg-danger hover:text-danger-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:pointer-events-none"
                >
                  <CloseIcon size={12} />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          disabled={disabled || full}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={commit}
        />
        <button
          type="button"
          aria-label={addLabel}
          disabled={disabled || full || draft.trim() === ""}
          onClick={commit}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border-strong text-text transition-colors hover:border-brand-line hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:pointer-events-none disabled:opacity-60"
        >
          <PlusIcon size={16} />
        </button>
      </div>
    </div>
  );
}
