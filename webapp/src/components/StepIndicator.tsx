/**
 * StepIndicator — numbered circles (1…N) joined by 2px connectors, with a
 * "Шаг N из M" subtitle (design-system §7, mockups IMG_0044/IMG_0046 top row).
 *
 * Visual states (token-driven, both themes):
 *   - done / active: flow-accent fill + --green-on glyph, connector before it filled
 *   - upcoming:      --surface fill + --border ring + --text-muted number
 *
 * Read-only — tapping a circle does NOT navigate (one-way wizard, UI-SPEC).
 * `accent` lets the seller wizard tint with --orange while the buyer keeps --green.
 */

import { Check } from "lucide-react";
import type { CSSProperties } from "react";

interface StepIndicatorProps {
  /** Current step (1-based). */
  current: number;
  /** Total number of steps. */
  total?: number;
  /** Flow accent for done/active circles. Defaults to the green primary. */
  accent?: string;
  /** Localized "Шаг N из M" subtitle (caller passes it for i18n). */
  subtitle?: string;
}

const CIRCLE = 28; // px

export default function StepIndicator({
  current,
  total = 4,
  accent = "var(--green)",
  subtitle,
}: StepIndicatorProps) {
  return (
    <div>
      <div
        role="status"
        aria-label={subtitle ?? `Шаг ${current} из ${total}`}
        style={{ display: "flex", alignItems: "center" }}
      >
        {Array.from({ length: total }, (_, i) => {
          const step = i + 1;
          const isPast = step < current;
          const isActive = step === current;
          const filled = isPast || isActive;

          const circle: CSSProperties = {
            flex: "0 0 auto",
            width: `${CIRCLE}px`,
            height: `${CIRCLE}px`,
            borderRadius: "var(--r-full)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "13px",
            fontWeight: 700,
            background: filled ? accent : "var(--surface)",
            color: filled ? "var(--green-on)" : "var(--text-muted)",
            border: filled ? "none" : "1px solid var(--border)",
          };
          const connector: CSSProperties = {
            flex: 1,
            height: "2px",
            background: isPast ? accent : "var(--border)",
          };

          return (
            <div key={step} style={{ display: "contents" }}>
              {i > 0 && <span style={connector} aria-hidden="true" />}
              <span style={circle} aria-current={isActive ? "step" : undefined}>
                {isPast ? <Check size={15} color="var(--green-on)" /> : step}
              </span>
            </div>
          );
        })}
      </div>

      {subtitle && (
        <p style={{ margin: "10px 0 0", fontSize: "12px", color: "var(--text-muted)" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
