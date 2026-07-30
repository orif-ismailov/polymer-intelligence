import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

import { IconTile } from "./IconTile";
import { AlertCircleIcon, CheckCircleOutlineIcon } from "./icons";
import { Spinner } from "./Spinner";

export type ChecklistState = "pending" | "running" | "passed" | "warning" | "failed";

interface ChecklistRowProps {
  icon?: ReactNode;
  title: string;
  /** Localized state line under the title — "Успешно", "Выполняется", … */
  status: string;
  state: ChecklistState;
  className?: string;
  "data-testid"?: string;
}

/** Tone of the glyph tile + state line, by outcome. */
const stateTone: Record<ChecklistState, { tile: "muted" | "brand" | "gold" | "danger"; text: string }> = {
  pending: { tile: "muted", text: "text-text-subtle" },
  running: { tile: "muted", text: "text-text-muted" },
  passed: { tile: "brand", text: "text-brand" },
  warning: { tile: "gold", text: "text-gold" },
  failed: { tile: "danger", text: "text-danger" },
};

function Mark({ state }: { state: ChecklistState }) {
  if (state === "running") return <Spinner />;
  if (state === "passed") {
    return (
      <span className="text-brand">
        <CheckCircleOutlineIcon size={22} />
      </span>
    );
  }
  if (state === "warning" || state === "failed") {
    return (
      <span className={state === "warning" ? "text-gold" : "text-danger"}>
        <AlertCircleIcon size={22} />
      </span>
    );
  }
  // Pending: an empty ring, so the row's height never jumps when it resolves.
  return (
    <span
      aria-hidden="true"
      className="block h-[22px] w-[22px] rounded-full border border-border-strong"
    />
  );
}

/**
 * One government-registry check on the registration «Проверка компании» sheet:
 * glyph tile, what is being checked, and how it came back — with the outcome
 * repeated as a mark on the right so the row reads at a glance without relying
 * on the colour of the status line alone.
 */
export function ChecklistRow({
  icon,
  title,
  status,
  state,
  className,
  "data-testid": testId,
}: ChecklistRowProps) {
  const tone = stateTone[state];
  return (
    <li
      className={cn("flex items-center gap-3 py-3", className)}
      data-testid={testId}
      data-state={state}
    >
      {icon ? (
        <IconTile tone={tone.tile} size="sm">
          {icon}
        </IconTile>
      ) : null}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-text">{title}</p>
        <p className={cn("mt-0.5 text-xs", tone.text)}>{status}</p>
      </div>
      <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center">
        <Mark state={state} />
      </span>
    </li>
  );
}
