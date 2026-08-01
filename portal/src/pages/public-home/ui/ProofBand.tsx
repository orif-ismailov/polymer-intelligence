import { type CSSProperties } from "react";

import {
  ArrowRight,
  Clock3,
  Globe2,
  LineChart,
  ShieldCheck,
  Signature,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { useReveal } from "@/shared/lib";
import { LinkButton } from "@/shared/ui";

import { BenefitCard } from "./BenefitCard";
import { PlatformFigures } from "./PlatformFigures";

/**
 * The five reasons, ranked. `verified` leads because it is the answer to the
 * question this whole band exists to settle — the others are why you would stay
 * once you believe that one.
 */
const BENEFITS = [
  { key: "verified", icon: ShieldCheck },
  { key: "prices", icon: LineChart },
  { key: "signing", icon: Signature },
  { key: "international", icon: Globe2 },
  { key: "support", icon: Clock3 },
] as const;

/**
 * The storefront's closing band: why this marketplace, proved, then the ask.
 *
 * It replaces two sections — a 120px trust strip with the join CTA wedged into
 * its sidebar, and a separate 22px stats bar under an `sr-only` heading. Both
 * were faithful reads of `marketplace.jpeg` and both gave the platform's trust
 * argument less design attention than a product card gets. Merged, the band runs
 * one arc: eyebrow → headline → supporting line → five reasons → the figures
 * that back them → a single CTA.
 *
 * **Full-bleed, but in the page's own materials.** Like `HeroBanner` it drops
 * the container so the band spans the viewport (`PublicShell` leaves `<main>`
 * unconstrained) and lets only the content re-enter the same `max-w-[1440px]`
 * grid every other section uses. What it does NOT borrow is the hero's
 * decoration: the blueprint ruling and the drifting brand orbs belong to a band
 * sitting on a photograph, and repeating them over a flat page made this section
 * read as a different product. The band is a tone step and a hairline — the same
 * `bg-surface` tint over `--bg` the hero's own metrics rail used — and the cards
 * on it are the page's cards: `rounded-md`, solid `bg-surface`, hairline border,
 * `DirectoryStrip`'s hover. Scale and layout carry the emphasis; nothing else
 * has to.
 *
 * Everything animates through one `data-revealed` flag on this root — see
 * `useReveal` for why the server must never render it.
 */
export function ProofBand() {
  const { t } = useTranslation();
  // `token !== null` — false during SSR and at first paint, so server and client
  // agree on the anonymous CTA and it swaps once the boot-time refresh resolves.
  // Nothing here issues an authenticated request; the page stays shared-cacheable.
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const { ref, revealed } = useReveal<HTMLElement>();

  return (
    <section
      ref={ref}
      aria-labelledby="why-heading"
      data-revealed={revealed === null ? undefined : String(revealed)}
      className="mt-6 border-t border-border bg-surface/40 lg:mt-10"
    >
      <div className="mx-auto w-full max-w-[1440px] px-4 py-14 sm:py-16 lg:px-6 xl:py-20">
        {/* Header. Seven of twelve so the measure stays readable at 1440 — a
            display line running the full container is a banner, not a sentence. */}
        <div className="max-w-[46rem]">
          <p
            data-reveal
            className="inline-flex items-center gap-2 rounded-full border border-brand-line bg-brand-soft px-3 py-1 text-[11px] font-medium text-brand sm:text-xs"
          >
            <Sparkles size={14} strokeWidth={2} aria-hidden />
            {t("public.home.whyEyebrow")}
          </p>

          {/* Clearly below the hero's `h1` (3.4rem at xl) so the page keeps one
              display voice and this reads as its answer, not its rival. It must
              stay an `h2`: `/` is asserted to have exactly one level-1 heading,
              in strict mode. */}
          <h2
            id="why-heading"
            data-reveal
            style={{ "--reveal-delay": "60ms" } as CSSProperties}
            className="mt-5 text-[1.625rem] font-semibold leading-[1.15] tracking-tight text-text sm:text-[2rem] xl:text-[2.375rem]"
          >
            {t("public.home.whyHeading")}
          </h2>

          <p
            data-reveal
            style={{ "--reveal-delay": "120ms" } as CSSProperties}
            className="mt-4 max-w-[52ch] text-[15px] leading-relaxed text-text-muted sm:text-base"
          >
            {t("public.home.whySubtitle")}
          </p>
        </div>

        {/* Bento. `verified` takes half the grid across both rows; the other
            four sit beside it as a 2x2. The asymmetry is what ranks them — the
            type scale only follows. Below `xl` it degrades to a plain 1- then
            2-column stack with the lead card spanning the full width. */}
        <ul className="mt-10 grid gap-3.5 sm:grid-cols-2 lg:mt-12 xl:grid-cols-12">
          {BENEFITS.map((benefit, index) => {
            const isHero = index === 0;
            return (
              <BenefitCard
                key={benefit.key}
                icon={benefit.icon}
                title={t(`public.home.why.${benefit.key}.title`)}
                // Revived on purpose. These sentences exist in all three locales
                // and were dropped from the old strip to hold it to the mockup's
                // height — which left five bare labels doing the persuading.
                body={t(`public.home.why.${benefit.key}.body`)}
                emphasis={isHero ? "hero" : "default"}
                delayMs={160 + index * 70}
                className={isHero ? "sm:col-span-2 xl:col-span-6 xl:row-span-2" : "xl:col-span-3"}
              />
            );
          })}
        </ul>

        <PlatformFigures revealed={revealed === true} />

        {/* The ask. A `surface` card with the accent edge — the same «chosen»
            treatment `Card variant="accent"` uses — rather than a brand-filled
            panel: a full `brand-soft` wash at this size stopped being an accent
            and became a second background. The green stays where it was in the
            band this replaces, on the heading and the button. Exactly one CTA —
            the hero already offers the browse-instead path, and repeating it
            here would split the close. */}
        <div
          data-reveal
          style={{ "--reveal-delay": "80ms" } as CSSProperties}
          // `items-start` while the panel is stacked: a flex column stretches
          // its children, which overrode the button's `sm:w-auto` and turned the
          // CTA into a full-bleed green bar from 640 to 1024.
          className="mt-14 flex flex-col items-start gap-6 rounded-md border border-brand-line bg-surface px-6 py-7 sm:px-8 lg:mt-16 lg:flex-row lg:items-center lg:justify-between lg:gap-10 lg:px-10"
        >
          <div className="min-w-0">
            <h3 className="text-xl font-semibold tracking-tight text-brand sm:text-2xl">
              {t("public.home.joinHeading")}
            </h3>
            <p className="mt-2 max-w-[46ch] text-sm leading-relaxed text-text-muted">
              {t("public.home.joinBody")}
            </p>
          </div>
          {/* «Регистрация компании» is the wrong ask of someone already signed
              in — the invitation has been accepted. Same slot, same weight,
              honest label. */}
          <LinkButton
            to={isAuthenticated ? "/cabinet" : "/cabinet/login"}
            size="lg"
            className="w-full shrink-0 px-8 sm:w-auto"
          >
            {t(isAuthenticated ? "common.cabinet" : "public.home.registerCompany")}
            <ArrowRight size={18} strokeWidth={2} aria-hidden />
          </LinkButton>
        </div>
      </div>
    </section>
  );
}
