"use client";

/**
 * NeedsReviewChip — "Needs Review" filter chip that renders disabled
 * with tooltip "Available after Phase 5 AI" per UI-SPEC §Signals/Offers.
 * Disabled in Phase 4 — Phase 5 AI needs_review queue wires this.
 */

import { useState } from "react";

export function NeedsReviewChip() {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        disabled
        aria-disabled="true"
        aria-describedby="needs-review-tooltip"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        onFocus={() => setShowTooltip(true)}
        onBlur={() => setShowTooltip(false)}
        className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-full border border-border bg-background-secondary px-3 py-1.5 text-xs font-semibold text-foreground-subtle opacity-50"
      >
        Needs Review
      </button>
      {showTooltip && (
        <div
          id="needs-review-tooltip"
          role="tooltip"
          className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-background-tertiary border border-border px-3 py-1.5 text-xs text-foreground shadow-lg z-10"
        >
          Available after Phase 5 AI
        </div>
      )}
    </div>
  );
}
