/**
 * useIsDesktop — reactive matchMedia hook driving the responsive chrome switch.
 *
 * Mobile-first: default styles target mobile; this only flips layout decisions
 * (bottom tab bar → top nav, centered max-width container) at the desktop breakpoint.
 */

import { useEffect, useState } from "react";

export const DESKTOP_QUERY = "(min-width: 900px)";

export function useIsDesktop(query: string = DESKTOP_QUERY): boolean {
  const read = () =>
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(query).matches;

  const [isDesktop, setIsDesktop] = useState<boolean>(read);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const handler = () => setIsDesktop(mq.matches);
    handler();
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [query]);

  return isDesktop;
}
