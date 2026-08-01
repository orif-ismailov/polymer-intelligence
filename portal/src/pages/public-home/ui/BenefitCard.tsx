import { type CSSProperties } from "react";

import { type LucideIcon } from "lucide-react";

import { cn } from "@/shared/lib";
import { IconTile } from "@/shared/ui";

interface BenefitCardProps {
  icon: LucideIcon;
  title: string;
  body: string;
  /**
   * `hero` is the one claim that answers "can I trust this marketplace at all"
   * and takes half the bento; everything else is a supporting reason. Callers
   * pick the rank, never the sizes.
   */
  emphasis?: "hero" | "default";
  /** Stagger offset, in ms, for the section's scroll-reveal. */
  delayMs: number;
  className?: string;
}

/**
 * One reason in the closing band's bento.
 *
 * The band it replaced rendered these as five equal 12px icon+label rows, which
 * gave the platform's whole trust argument the visual weight of a footnote and
 * dropped the `why.*.body` sentences entirely to stay inside the mockup's 120px.
 * Here they are cards with room for the body copy, and the grid — not the type
 * scale — carries the ranking.
 *
 * Deliberately NOT a link. Two of the five reasons have a plausible destination
 * (`/manufacturers`, `/prices`) and three have none; a grid where some cards
 * navigate and others don't is a worse affordance than one where none do. These
 * are claims, and the band's single CTA is where the conversion lives. The hover
 * response is the house pattern from `DirectoryStrip` all the same — the cards
 * acknowledge the cursor, they just don't promise a page.
 */
export function BenefitCard({
  icon: Icon,
  title,
  body,
  emphasis = "default",
  delayMs,
  className,
}: BenefitCardProps) {
  const isHero = emphasis === "hero";

  return (
    <li
      data-reveal
      style={{ "--reveal-delay": `${delayMs}ms` } as CSSProperties}
      className={cn(
        // Exactly the card `DirectoryStrip` draws, one section up the page:
        // `rounded-md`, solid surface, hairline, and the same hover. The lead
        // card differs only in the accent edge — the established "this one is
        // chosen" signal — and in how much of the grid it takes.
        "group flex flex-col rounded-md border bg-surface transition-colors",
        "hover:border-brand-line hover:bg-surface-2",
        isHero ? "border-brand-line p-6 lg:p-7" : "border-border p-5",
        className,
      )}
    >
      <IconTile
        tone={isHero ? "brand" : "muted"}
        size={isHero ? "md" : "sm"}
        className="group-hover:border-brand-line group-hover:bg-brand-soft group-hover:text-brand"
      >
        <Icon size={isHero ? 22 : 18} strokeWidth={1.75} aria-hidden />
      </IconTile>

      {/* The lead card is the only one whose height is not its content's: at
          `xl` it spans both bento rows, which leaves it taller than the two
          cards stacked beside it, and letting the copy sit up under the glyph
          turned that surplus into a hole at the bottom. Anchoring the text to
          the floor makes the extra height read as measure instead.
          Scoped to `xl` on purpose — below it the row-span collapses and the
          card is content-height, where the same padding is just a gap. */}
      <div className={isHero ? "mt-5 xl:mt-auto xl:pt-10" : "mt-4"}>
        <h3
          className={cn(
            "font-semibold leading-snug tracking-tight text-text",
            isHero ? "text-lg" : "text-[15px]",
          )}
        >
          {title}
        </h3>
        <p
          className={cn(
            "leading-relaxed text-text-muted",
            isHero ? "mt-3 max-w-[42ch] text-sm" : "mt-2 text-xs",
          )}
        >
          {body}
        </p>
      </div>
    </li>
  );
}
