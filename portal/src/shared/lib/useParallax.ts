import { useEffect, useRef, type RefObject } from "react";

/**
 * Scroll-linked parallax for a full-bleed backdrop, e.g. the storefront hero's
 * photograph.
 *
 * The element lags the page as it scrolls, which needs somewhere to lag INTO —
 * so the caller magnifies it and this hook slides it within the margin that
 * creates. Two things follow from where that margin comes from:
 *
 * - **The scale lives in CSS, not here.** The caller sets `--parallax-scale`
 *   in a `motion-safe:` class, so it is present in the server HTML and applied
 *   at first paint; a scale applied from JS on mount would pop the photo 20%
 *   larger the moment hydration finished. This hook reads the property back to
 *   work out how far it may travel, so the two can never disagree.
 * - **Reduced motion disables it for free.** Under `prefers-reduced-motion` the
 *   `motion-safe:` rules never match, `--parallax-scale` resolves to nothing,
 *   the headroom is 0 and every shift clamps to 0. The explicit media check
 *   below is belt-and-braces: it also skips attaching the listeners at all.
 *
 * The element's `parentElement` is the band being scrolled through, and its
 * distance above the viewport top is the whole input — no page-level scroll
 * offset, so it keeps working wherever the band sits.
 *
 * **SSR-safe.** All of it runs in an effect, so the server emits the photo with
 * no transform and the page is complete without JS; the parallax is purely
 * additive. Nothing here re-renders React — the scroll handler writes one
 * custom property, `transform` stays on the compositor, and the listener is
 * only attached while the band is actually on screen.
 */
export function useParallax<T extends HTMLElement>(depth = 0.07): RefObject<T> {
  // `useRef<T>(null)`, not `useRef<T | null>` — the former resolves to
  // `RefObject<T>`, which is what React 18 accepts for a `ref` prop. Same call
  // shape `useReveal` uses.
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    const host = el?.parentElement;
    if (!el || !host) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;

    const apply = (): void => {
      frame = 0;
      const rect = host.getBoundingClientRect();
      // The magnification the caller asked for, halved: a `scale()` grows the
      // element around its centre, so the slack is split between top and bottom.
      const scale = Number.parseFloat(
        getComputedStyle(el).getPropertyValue("--parallax-scale"),
      );
      const headroom = Number.isFinite(scale) ? (rect.height * (scale - 1)) / 2 : 0;
      if (headroom <= 0) return;

      // `-rect.top` is how far the band's top has travelled above the viewport
      // top. The photo follows at a fraction of that, so it drifts DOWN the
      // frame relative to the copy on top of it, and stops once it runs out of
      // slack.
      //
      // Floored at 0 rather than allowed to go negative, so the composition the
      // hero was framed for IS the resting state. Letting it run both ways put
      // the photo 11px off its intended crop at the top of the page — the one
      // view every visitor sees, and the one the `object-position` values above
      // were chosen against.
      const shift = Math.min(headroom, Math.max(0, -rect.top * depth));
      el.style.setProperty("--parallax-y", `${shift.toFixed(2)}px`);
    };

    const onScroll = (): void => {
      // Coalesce to one write per frame; scroll fires far more often than that.
      if (frame === 0) frame = requestAnimationFrame(apply);
    };

    // Spelled out rather than picking `add`/`removeEventListener` into a
    // variable: detaching either from `window` loses its receiver, which is
    // what `@typescript-eslint/unbound-method` objects to.
    const listen = (on: boolean): void => {
      if (on) {
        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onScroll, { passive: true });
      } else {
        window.removeEventListener("scroll", onScroll);
        window.removeEventListener("resize", onScroll);
      }
    };

    // Off-screen the band cannot show any drift, so there is nothing to compute.
    let observer: IntersectionObserver | undefined;
    if (typeof IntersectionObserver === "undefined") {
      listen(true);
    } else {
      observer = new IntersectionObserver(
        (entries) => {
          const on = entries.some((entry) => entry.isIntersecting);
          listen(on);
          if (on) apply();
        },
        { rootMargin: "10% 0px" },
      );
      observer.observe(host);
    }

    apply();

    return () => {
      observer?.disconnect();
      listen(false);
      if (frame !== 0) cancelAnimationFrame(frame);
      el.style.removeProperty("--parallax-y");
    };
  }, [depth]);

  return ref;
}
