import { type ReactNode, useCallback, useId, useRef, useState } from "react";

import { createPortal } from "react-dom";

import { cn } from "@/shared/lib";

export type TooltipPlacement = "top" | "right";

interface TooltipProps {
  content: string;
  children: ReactNode;
  /**
   * Where the bubble sits relative to the trigger. `"right"` exists for the
   * collapsed cabinet rail, where `"top"` would put the label over the nav row
   * above instead of beside the icon it describes.
   */
  placement?: TooltipPlacement;
  className?: string;
}

const BUBBLE =
  "pointer-events-none z-50 whitespace-nowrap rounded-md bg-text px-2 py-1 text-xs text-bg shadow-md";

/**
 * Hover/focus tooltip. Dependency-free — the trigger owns focus, and the bubble
 * is associated via `aria-describedby` for screen readers.
 *
 * It is a *supplement* to an accessible name, never a replacement: a trigger
 * that renders no text of its own still needs its own `aria-label`.
 *
 * **`top` is CSS-only; `right` is portalled.** The difference is not stylistic.
 * A `right` bubble is used by the collapsed rail, whose nav sits in a scroll
 * container — and a scroll container clips on BOTH axes. Setting only
 * `overflow-y: auto` does not opt out of that: CSS computes a `visible` axis to
 * `auto` when the other one is not visible, so `overflow-x` becomes `auto` too.
 * Measured on the live rail, the bubble ran x 57→119 inside a box that ended at
 * 63 — six visible pixels. No amount of `z-index` escapes an ancestor's clip;
 * only leaving the subtree does. So `right` renders into `document.body` and
 * positions itself off the trigger's rect.
 *
 * `top` keeps the pure-CSS path deliberately: it has call sites that are not in
 * a scroll container, and this way none of them gain a state update on hover.
 */
export function Tooltip({ content, children, placement = "top", className }: TooltipProps) {
  const id = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  // Non-null only while a `right` tooltip is open — which is also the guard that
  // keeps `createPortal` away from SSR, where `document` does not exist. A
  // pointer event cannot fire on the server, so the branch is never reached.
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);

  const isPortalled = placement === "right";

  const show = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    // `position: fixed`, so viewport coordinates — no offset-parent maths, and
    // it survives being spawned from inside a scrolled rail.
    setCoords({ top: rect.top + rect.height / 2, left: rect.right + 8 });
  }, []);
  const hide = useCallback(() => setCoords(null), []);

  if (!isPortalled) {
    return (
      <span className={cn("group relative inline-flex", className)}>
        <span aria-describedby={id}>{children}</span>
        <span
          role="tooltip"
          id={id}
          className={cn(
            BUBBLE,
            "absolute bottom-full left-1/2 mb-2 -translate-x-1/2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100",
          )}
        >
          {content}
        </span>
      </span>
    );
  }

  return (
    <span
      ref={triggerRef}
      className={cn("relative inline-flex", className)}
      onPointerEnter={show}
      onPointerLeave={hide}
      // Keyboard parity: the label has to appear on tab-through too, or the
      // collapsed rail is legible by mouse only.
      onFocusCapture={show}
      onBlurCapture={hide}
    >
      {/* `flex w-full` so a trigger asking to fill its row actually can. The
          measured rect is this wrapper's, so a full-width trigger also puts the
          bubble clear of the rail's edge instead of 7px over its border. */}
      <span className="flex w-full" aria-describedby={coords ? id : undefined}>
        {children}
      </span>
      {coords
        ? createPortal(
            <span
              role="tooltip"
              id={id}
              style={{ top: coords.top, left: coords.left }}
              className={cn(BUBBLE, "fixed -translate-y-1/2")}
            >
              {content}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}
