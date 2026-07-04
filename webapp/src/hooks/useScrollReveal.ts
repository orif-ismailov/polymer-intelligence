/**
 * useScrollReveal — lightweight IntersectionObserver scroll-reveal (no animation deps).
 *
 * Attach the returned ref to a container; every descendant marked `data-reveal`
 * gets `data-visible="true"` the first time it scrolls into view. Reduced-motion
 * users and browsers without IntersectionObserver get everything revealed up front.
 * Pairs with the Tailwind `data-[visible=true]:` reveal utilities in Landing.tsx.
 */

import { useEffect, useRef } from "react";

export function useScrollReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;

    const els = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"));

    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    if (prefersReduced || typeof IntersectionObserver === "undefined") {
      els.forEach((el) => (el.dataset.visible = "true"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.visible = "true";
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );

    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return ref;
}
