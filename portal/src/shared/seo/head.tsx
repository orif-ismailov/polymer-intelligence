import { useContext, useEffect, type ReactNode } from "react";

import {
  applyHeadToDocument,
  HeadContext,
  type HeadSink,
  type SeoData,
} from "./headContext";

/**
 * A minimal, SSR-first document-head manager.
 *
 * Hand-rolled rather than pulled from a library: `react-helmet-async` is
 * archived, React 18 has no native metadata hoisting (that landed in 19), and
 * what this app needs is six tag shapes, not a general-purpose head engine.
 *
 * - **Server.** `renderToString` walks the tree, every `<Seo/>` writes into the
 *   sink on the context, and `renderHeadTags()` serializes the winner AFTER the
 *   render returns. Last write wins, so a nested route overrides the shell.
 * - **Browser.** There is no sink, so `<Seo/>` patches `document.head` through
 *   an effect instead. That path is for client-side navigation, where the head
 *   the server sent belongs to a different URL.
 */

export function HeadProvider({
  sink,
  children,
}: {
  sink: HeadSink | null;
  children: ReactNode;
}) {
  return <HeadContext.Provider value={sink}>{children}</HeadContext.Provider>;
}

/**
 * Declare this page's head. Render it anywhere in the tree; the deepest one to
 * render wins, so a route overrides the shell's defaults.
 */
export function Seo(data: SeoData) {
  const sink = useContext(HeadContext);

  // Server: write straight into the sink during render. A side effect in a
  // render function is normally wrong; it is correct here because the sink is
  // created per request and discarded once `renderToString` returns, so there is
  // no state to tear and nothing to re-render.
  if (sink) {
    sink.current = { ...sink.current, ...data };
  }

  // Serialized identity, so the effect re-runs when a VALUE changes rather than
  // on every parent render (the `data` object is new each time).
  const key = JSON.stringify(data);

  useEffect(() => {
    if (typeof document === "undefined") return;
    applyHeadToDocument(JSON.parse(key) as SeoData);
  }, [key]);

  return null;
}
