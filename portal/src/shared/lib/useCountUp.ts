import { useEffect, useRef, useState } from "react";

import { useIsomorphicLayoutEffect } from "./useReveal";

interface CountUpOptions {
  /** Flip true when the figure scrolls into view — see `useReveal`. */
  enabled?: boolean;
  /** Decimal places to hold while counting, so "99,8%" doesn't jitter. */
  decimals?: number;
  durationMs?: number;
}

function allowsMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function round(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/**
 * Counts a figure up to `target` once it is revealed.
 *
 * The ordering is the whole point, and it runs opposite to the obvious one:
 *
 * 1. State starts at `target`, so the **server renders the real number**. This
 *    page is indexed — a crawler that saw `0` would record `0`, and a visitor
 *    without JS would keep it.
 * 2. On the client, a *layout* effect drops it to `0` before first paint. The
 *    obvious "start at 0, count up" would emit `0` into the SSR HTML; starting
 *    at the answer and reversing that pre-paint gets the animation without ever
 *    putting a wrong number on the wire.
 * 3. `enabled` then animates `0 → target` on an ease-out cubic.
 *
 * Under `prefers-reduced-motion: reduce` step 2 never happens, so the figure is
 * simply correct from the first frame — no gate needed at the call site.
 */
export function useCountUp(
  target: number,
  { enabled = true, decimals = 0, durationMs = 1100 }: CountUpOptions = {},
): number {
  const [value, setValue] = useState(target);
  const hasRun = useRef(false);

  useIsomorphicLayoutEffect(() => {
    if (allowsMotion()) setValue(0);
  }, []);

  useEffect(() => {
    if (!allowsMotion()) {
      setValue(target);
      return;
    }
    // A `target` that arrives after the animation has run (stats resolving
    // late): snap to it, don't re-count.
    if (hasRun.current) {
      setValue(target);
      return;
    }
    // Not in view yet. Hold at the 0 the layout effect set — snapping to
    // `target` here would undo it and there would be nothing left to animate.
    if (!enabled) return;

    hasRun.current = true;
    let frame = 0;
    let startedAt = 0;

    const step = (now: number): void => {
      if (startedAt === 0) startedAt = now;
      const progress = Math.min(1, (now - startedAt) / durationMs);
      const eased = 1 - (1 - progress) ** 3;
      setValue(round(target * eased, decimals));
      if (progress < 1) frame = requestAnimationFrame(step);
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [enabled, target, decimals, durationMs]);

  return value;
}
