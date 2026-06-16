/**
 * StepIndicator — 4-dot progress indicator for the wizard steps.
 *
 * Visual states:
 *   - active step: accent fill (--tg-theme-button-color)
 *   - past steps:  accent outline (border: 1px solid accent, transparent fill)
 *   - future steps: hint fill (--tg-theme-hint-color)
 *
 * Read-only visual — tapping dots does NOT navigate (one-way wizard, UI-SPEC).
 */

const DOT_SIZE = 8; // px — UI-SPEC: 8px diameter
const DOT_GAP = 4;  // px — xs spacing token

interface StepIndicatorProps {
  /** Current step (1-based). */
  current: number;
  /** Total number of steps. */
  total?: number;
}

export default function StepIndicator({ current, total = 4 }: StepIndicatorProps) {
  return (
    <div
      aria-label={`Шаг ${current} из ${total}`}
      role="status"
      style={{
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: `${DOT_GAP}px`,
      }}
    >
      {Array.from({ length: total }, (_, i) => {
        const step = i + 1;
        const isPast = step < current;
        const isActive = step === current;
        // future: step > current

        return (
          <div
            key={step}
            aria-current={isActive ? "step" : undefined}
            style={{
              width: `${DOT_SIZE}px`,
              height: `${DOT_SIZE}px`,
              borderRadius: "50%",
              backgroundColor: isActive
                ? "var(--tg-theme-button-color, #10b981)"
                : isPast
                  ? "transparent"
                  : "var(--tg-theme-hint-color, #94a3b8)",
              border: isPast
                ? "1.5px solid var(--tg-theme-button-color, #10b981)"
                : "none",
              flexShrink: 0,
            }}
          />
        );
      })}
    </div>
  );
}
