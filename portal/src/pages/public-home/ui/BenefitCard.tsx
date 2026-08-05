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
        // Tighter on a phone, where a supporting card is 174px wide and `p-5`
        // spent a fifth of that on air.
        isHero ? "border-brand-line p-5 sm:p-6 lg:p-7" : "border-border p-3.5 sm:p-5",
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
      <div className={isHero ? "mt-4 sm:mt-5 xl:mt-auto xl:pt-10" : "mt-3 sm:mt-4"}>
        {/*
          `leading-snug` / `leading-relaxed` here are, and always were, dead on
          the NAMED sizes: `cn` is `tailwind-merge`, which treats a `text-{size}`
          as conflicting with `leading-*` (Tailwind's named sizes ship a
          line-height) and drops the leading that came before it. So the hero
          title has rendered at `text-lg`'s 28px, not snug's 24.75px, since it
          was written — and the phone sizes below inherit the same rule.

          Left exactly as it was on purpose. Repeating the leading per
          breakpoint would "fix" it into a different desktop composition, which
          is a change to make deliberately, not as a side effect of a mobile
          pass. They survive on `text-[13px]`/`text-[15px]`, because an
          arbitrary size sets font-size only and twMerge does not treat it as a
          conflict.
        */}
        <h3
          className={cn(
            "font-semibold leading-snug tracking-tight text-text",
            isHero ? "text-base sm:text-lg" : "text-[13px] sm:text-[15px]",
          )}
        >
          {title}
        </h3>
        <p
          className={cn(
            "leading-relaxed text-text-muted",
            isHero
              ? "mt-2 max-w-[42ch] text-[13px] sm:mt-3 sm:text-sm"
              : "mt-1.5 text-[11px] sm:mt-2 sm:text-xs",
          )}
        >
          {body}
        </p>
      </div>
    </li>
  );
}
