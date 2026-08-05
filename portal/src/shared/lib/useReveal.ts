import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

/**
 * `useLayoutEffect` warns when it runs during `renderToString`, and the
 * storefront is server-rendered. The layout timing is what matters on the
 * client (see below), so take it there and fall back to `useEffect` on the
 * server, where neither one runs anyway.
 */
export const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export interface Reveal<T extends HTMLElement> {
  ref: RefObject<T>;
  /**
   * `null` until the client takes over — deliberately three-valued. See the
   * SSR note below; `false` is "hidden, about to animate", which is not a state
   * the server may ever emit.
   */
  revealed: boolean | null;
}

/**
 * Scroll-reveal for a whole section, driven by one flag on its root.
 *
 * The section marks its animatable children with `data-reveal` (and an optional
 * `--reveal-delay` for the stagger), and renders `data-revealed` on the root
 * from this hook's state. The CSS in `app/styles.css` does the rest, so the
 * stagger costs one observer per band and zero re-renders per card. The boolean
 * comes back out as well because the counters need it in JS, not just in CSS.
 *
 * **The server must not render the hidden state.** This page is SSR'd and
 * indexed, so `revealed` starts `null` and the attribute is omitted entirely
 * from the HTML a crawler — or a visitor whose JS never arrives — receives.
 * Neither CSS rule matches without it, so the default is "visible" and the
 * animation is purely additive on top of a page that already works. It is also
 * what keeps hydration quiet: server and first client render both emit no
 * attribute.
 *
 * The flip to `false` happens in a *layout* effect so the hide lands before the
 * browser paints. A passive effect would show the band, hide it, then animate it
 * back in — a visible flicker whenever the band is already on screen at mount.
 */
export function useReveal<T extends HTMLElement>(): Reveal<T> {
  const ref = useRef<T>(null);
  const [revealed, setRevealed] = useState<boolean | null>(null);

  useIsomorphicLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;

    // No observer (very old browsers, some crawlers' renderers): reveal at once
    // rather than leave the section hidden forever.
    if (typeof IntersectionObserver === "undefined") {
      setRevealed(true);
      return;
    }

    setRevealed(false);

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setRevealed(true);
        // Fires once. The band never re-hides on the way back up — a section
        // that re-animates every time it re-enters the viewport reads as a
        // glitch, not as polish.
        observer.disconnect();
      },
      // A little short of the true edge so the entrance starts while the band is
      // still arriving, not after it has already come to rest.
      { rootMargin: "0px 0px -12% 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, revealed };
}
