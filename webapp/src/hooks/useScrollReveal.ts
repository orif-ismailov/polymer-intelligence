/**
 * useScrollReveal — lightweight IntersectionObserver scroll-reveal (no animation deps).
 *
 * Attach the returned ref to a container; every descendant marked `data-reveal`
 * gets the `is-visible` class the first time it scrolls into view. Reduced-motion
 * users and browsers without IntersectionObserver get everything revealed up front.
 * Pairs with the `.reveal` / `.is-visible` rules in landing.css.
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
      els.forEach((el) => el.classList.add("is-visible"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
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
