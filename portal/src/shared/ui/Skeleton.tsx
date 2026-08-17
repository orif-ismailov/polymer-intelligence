import { cn } from "@/shared/lib";

interface SkeletonProps {
  className?: string;
}

/**
 * Loading placeholder.
 *
 * A `<span class="block">`, not a `<div>`, and that is load-bearing rather than
 * cosmetic. Placeholders stand in for text, so they get written inside `<p>` —
 * and a `<div>` inside a `<p>` is invalid HTML that the parser "fixes" by
 * closing the paragraph early. On a server-rendered page that is fatal: the DOM
 * the browser builds can never match the tree React renders, hydration fails,
 * and the whole root silently falls back to client rendering — throwing away
 * the SSR this app exists to do for crawlers. (Real symptom, on the public home
 * page's directory cards, whenever the stats prefetch had not resolved.)
 *
 * `block` keeps the box identical to the old `<div>`, so sizes and flex/grid
 * behaviour at the 61 call sites are unchanged; `span` just makes it phrasing
 * content, which is legal everywhere including inside a paragraph.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <span
      className={cn("block animate-pulse rounded-md bg-surface-2", className)}
      aria-hidden="true"
    />
  );
}
