import { useTranslation } from "react-i18next";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { useParallax } from "@/shared/lib";
import { LinkButton } from "@/shared/ui";

import { HeroSearch } from "./HeroSearch";

/**
 * React 18 does not know the camelCase `fetchPriority` prop — that landed in
 * React 19, and passing it here logs a DOM-attribute warning on every render.
 * The lowercase HTML attribute is what the preload scanner actually reads, and
 * React forwards unknown all-lowercase attributes untouched.
 */
const FETCH_PRIORITY_HIGH: Record<string, string> = { fetchpriority: "high" };

/**
 * The storefront's opening band — full-bleed, edge to edge.
 *
 * It used to be a contained card: `marketplace.jpeg` §2 measures 24,77 →
 * 1415,431 on the 1440 layout, so the hero inherited the page container and
 * carried its own radius and hairline. That is a faithful read of the mockup and
 * a poor landing page. The card's own border cut it off from the nav above and
 * the directory strip below, its 431px could not hold a display headline, and
 * at 1440 the copy ran out around x=460 with the remaining two thirds carrying
 * nothing but photograph.
 *
 * What replaced it keeps every piece of that composition — same photo, same
 * copy, same search, same four metrics — and re-hangs them on the full viewport:
 *
 * - **The section drops the container; only its contents re-enter it.** The
 *   image and the scrims span `100%` of `<main>`, which `PublicShell` leaves
 *   unconstrained, while the copy sits back inside the same `max-w-[1440px]`
 *   grid every other section on the page uses. Full-bleed backdrop, aligned
 *   foreground.
 * - **Both ends dissolve into `--bg`.** The vertical scrim resolves to the page
 *   colour at the top, under the sticky header, and again at the foot, where the
 *   metrics rail begins — so the hero has no visible upper or lower edge and
 *   reads as the top of the page rather than as its first card. This is why the
 *   header needs no change: it is already `bg-bg/95`, and it now meets an
 *   identical colour.
 * - **The metrics left the page entirely.** They used to close this band as a
 *   four-cell rail, which restated products / companies / countries roughly a
 *   screen above the closing `ProofBand` that now states them at display size.
 *   One page saying the same three numbers twice weakens both, so the figures
 *   belong to the close and the hero keeps the qualitative promise: the
 *   headline and the search. What the rail also provided was the seam into the
 *   directory cards — that job passes to this section's own bottom hairline,
 *   which reaches both viewport edges the same way the rail's did.
 * - **The scrims fall off rather than thin out.** An earlier stack held a heavy
 *   wash across the whole band, which bought contrast everywhere and cost the
 *   photograph — the trade-route map that is the reason this image was chosen
 *   was barely legible under it. What replaced it keeps the scrim strong where
 *   the copy sits and drops it to nothing across the right, where no text is
 *   painted. Same protection, applied where it is needed instead of uniformly.
 */
export function HeroBanner() {
  const { t } = useTranslation();
  // `token !== null` — false during SSR and at first paint, so the server and
  // the hydrating client agree on the anonymous copy and the CTA swaps once the
  // boot-time refresh resolves. Same contract the header runs on; nothing here
  // issues an authenticated request, so the page stays shared-cacheable.
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  // Drifts the photograph against the copy on scroll. Everything it needs is in
  // the `<img>`'s own classes below; see `useParallax` for why the scale is CSS
  // and the offset is JS.
  const parallaxRef = useParallax<HTMLImageElement>();

  return (
    <section
      aria-labelledby="hero-heading"
      className="relative isolate overflow-hidden "
    >
      {/*
        A real <img>, not a CSS background. This page is server-rendered, so the
        element is in the HTML the browser receives and the preload scanner can
        start the LCP fetch before any stylesheet resolves; a background-image is
        invisible until the CSSOM exists. Decorative — the headline beside it
        already says what it says.
      */}
      <img
        ref={parallaxRef}
        src="/banner_left_cleared.jpg"
        alt=""
        aria-hidden
        decoding="async"
        {...FETCH_PRIORITY_HIGH}
        /*
         * The banner is 1717x916 and this band is far wider than it is tall, so
         * `cover` scales to WIDTH and crops the vertical. 30% is the band that
         * keeps the trade-route map whole: lower and РОССИЯ / КАЗАХСТАН get
         * sliced through, which reads as an accident rather than a crop. On a
         * phone the frame is nearly square, so it re-centres on the skyline.
         *
         * The parallax rides on top of that, and deliberately does NOT touch the
         * element's box: growing `h-full` to make room would drop the frame
         * below the image's own 1.87 aspect and flip `cover` from width-driven
         * to height-driven, re-cropping the map sideways. A `scale()` leaves the
         * box — and therefore every `object-*` decision above — exactly as it
         * was and just magnifies what is already framed.
         *
         * 1.08, and the ceiling is the photograph, not taste. The slack a
         * parallax can spend is (scale-1)/2 of the band's height, so a bigger
         * number buys a longer drift — but it buys it by cropping, and this
         * frame has labels at its edges. At 1.2 the visible area falls to 83%
         * and the trade route loses РОССИЯ off the top and КИТАЙ off the side,
         * which is precisely the "reads as an accident rather than a crop"
         * failure the object-position note above exists to avoid. 1.08 keeps
         * 93% of the frame — every label still whole — for ~26px of travel on
         * the desktop hero and ~24px on a phone.
         *
         * `motion-safe:` on all three: without it a visitor who asked for
         * reduced motion would still get the crop change, which is the part
         * they can see standing still.
         */
        className="absolute inset-0 -z-10 h-full w-full object-cover object-[62%_45%] lg:object-[50%_30%] motion-safe:[--parallax-scale:1.08] motion-safe:[transform:translate3d(0,var(--parallax-y,0px),0)_scale(var(--parallax-scale))] motion-safe:[will-change:transform]"
      />

      {/*
        Scrim stack, in order. Each is `--bg` at some strength, so the hero is
        always the page colour thinned over a photo rather than a grey wash.
      */}
      {/* 1. Vertical: solid at both ends, thin through the middle. This is the
             layer that removes the seam under the header and the seam into the
             rail, which is why its two END stops stay at `--bg`.

             The middle came down 30/20 → 20/15 and no further, and the ceiling
             is measured rather than chosen. Because this layer spans the full
             width it is the only one that veils the photo's focal points — the
             tower at 51%vw, the map at 66%, the refinery at 87% — so every
             point taken off it is a point the picture gains everywhere. It is
             ALSO the only scrim over the subtitle's lower half. Taken to 10/5
             the desktop subtitle measured 4.13:1 dark and 3.95:1 light, and
             layer 3 could not recover it: the worst pixels sit at 29–36%vw,
             already inside layer 3's held zone, so raising THAT bought 0.25 and
             stalled. 20/15 is where both themes clear AA with the picture still
             legible end to end.

             `dark:to-bg` is not redundant with `to-bg`, and leaving it off is a
             bug this band shipped with. A `via-*` utility ALSO writes
             `--tw-gradient-to` (the transparent fallback a two-stop gradient
             needs), and Tailwind emits variants after unprefixed utilities — so
             `dark:via-bg/15` lands after `to-bg` and clobbers it. In the default
             dark theme the end stop was resolving to `rgb(255 255 255 / 0)`,
             i.e. the bottom of the hero faded to transparent white and never
             met the page colour at all. Any `dark:via-*` needs a `dark:to-*`
             beside it. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-gradient-to-b from-bg via-bg/20 to-bg dark:via-bg/15 dark:to-bg"
      />
      {/* 2. Phone/tablet: a flat scrim, because there is no side-by-side to
             separate — the copy sits ON the picture and needs a floor under it.
             There is no falloff to tune here (the text spans the full width, so
             a horizontal one would have nowhere to fall off TO), which is why
             this layer alone is a straight reduction: 90% → 80%.

             80 is the floor, not a preference. 65% put the subtitle at 3.85:1
             dark / 4.03:1 light and the popular-query label at 4.33 / 3.79 —
             the same failure the old note recorded at 70% (1.85:1 against the
             sunlit sky), which is what the 90% was for. 75% still left the light
             label at 4.35. At 80% the worst run on a phone is 4.77:1. Ten points
             is a modest gain for the picture, and it is all a full-width scrim
             under full-width text can give: the next move would be a text-shadow
             or a local pad behind the copy, and the design system has neither.

             80 and not 78: a BARE opacity modifier has to come from
             `theme.opacity`, which steps by 5. `bg-bg/78` compiles to nothing at
             all, silently, exactly like an undefined colour would. */}
      <div aria-hidden className="absolute inset-0 -z-10 bg-bg/80 lg:hidden" />
      {/* 3. Desktop: the horizontal one that creates the two-part composition —
             copy at the left, photo breathing at the right. This is the layer
             that protects text, and it is shaped to do only that.

             The old ramp started falling immediately (70/55% by the midpoint,
             still 15/5% at the far edge): weakest where the copy needed it, and
             never absent where the photograph did. This one inverts both ends.
             It HOLDS its anchor flat to 38%vw — past the right edge of both the
             headline's `max-w-[22ch]` and the subtitle's `44ch` — then falls to
             a true zero. So the copy sits on more scrim than it used to (95/80
             against the old 85/70), while the five empty grid columns this
             composition exists to show are clear from 60%vw out.

             The anchor is stronger than the old one on purpose: it is the knob
             that costs the picture nothing. Everything it darkens is left of
             38%vw, where the design has already committed the space to text —
             no focal point of the frame is in there. Reach for it before layer
             1, whose every point is paid for across the whole band.

             `to-bg/0` and not `to-transparent`: every stop in this stack is
             `--bg` at some strength, and the bare keyword would fade toward
             transparent BLACK instead of the page's own hue. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 hidden bg-gradient-to-r from-bg/95 from-38% via-bg/45 via-60% to-bg/0 lg:block dark:from-bg/80 dark:via-bg/20 dark:to-bg/0"
      />
      {/* 4. Brand light behind the headline. The one warm element in the stack,
             drifting slowly so the band is not completely static. Kept weak on
             purpose: the palette is "near-black graphite with ONE bright
             accent", and at the 20% this started on it stopped being a light
             behind the headline and became a green wash over the left half. */}
      <div
        aria-hidden
        className="absolute -left-32 top-[38%] -z-10 h-[26rem] w-[26rem] -translate-y-1/2 rounded-full bg-[radial-gradient(circle_at_center,color-mix(in_srgb,var(--brand)_9%,transparent),transparent_70%)] motion-safe:animate-hero-drift"
      />
      {/* 5. Blueprint grid, ruled in the same hairline as every card, masked so
             it never reaches the photograph. */}
      <div aria-hidden className="hero-grid absolute inset-0 -z-10 opacity-60" />

      {/* Asymmetric bottom padding: the rail used to add ~72px of its own below
          the copy, and dropping it without giving that height back left the CTAs
          sitting on the hairline. */}
      <div className="mx-auto w-full max-w-[1440px] px-4 pb-11 pt-8 sm:pb-20 sm:pt-14 lg:px-6 xl:pb-24 xl:pt-20">
        {/* Seven of twelve, and the other five are deliberately empty: that is
            where the photo's focal point lives (the trade-route map and the
            skyline). The grid states the split rather than a `max-w` that just
            happens to stop in the right place. */}
        <div className="grid items-center gap-10 xl:grid-cols-12">
          <div className="min-w-0 motion-safe:animate-hero-rise xl:col-span-7">
            {/* The display rung. It lives here rather than in `PageHeader`
                because that primitive owns the *page title* scale (24px) — this
                is a landing headline, the one place the storefront outranks it,
                and there is exactly one of them in the app.

                No top margin: an eyebrow chip used to sit above this, and the
                `mt-4 sm:mt-5` that cleared it became a stray offset the moment
                the chip went. The container's own `pt-8 sm:pt-14 xl:pt-20` is
                what sets the headline off the header now. */}
            <h1
              id="hero-heading"
              className="max-w-[22ch] text-[2rem] font-semibold leading-[1.1] tracking-tight text-text sm:text-[2.6rem] xl:text-[3.4rem] xl:leading-[1.06]"
            >
              {t("public.home.heroTitle")}
            </h1>

            <p className="mt-3 max-w-[44ch] text-[15px] leading-relaxed text-text-muted sm:mt-5 sm:text-lg">
              {t("public.home.heroSubtitle")}
            </p>

            <div className="mt-5 sm:mt-8">
              <HeroSearch />
            </div>

            {/*
              Two actions beside the search, not instead of it: search converts a
              visitor who knows what they want, and these convert the one who is
              still deciding whether this is the right marketplace at all.

              The primary swaps with the session — never to «Войти», which would
              put a sign-in link on a page the visitor is already signed into.
            */}
            <div className="mt-5  hidden flex-col gap-2.5 sm:mt-7 sm:flex-row sm:items-center sm:gap-3">
              <LinkButton
                to={isAuthenticated ? "/cabinet" : "/cabinet/login"}
                size="lg"
                className="w-full px-8 sm:w-auto"
              >
                {t(
                  isAuthenticated
                    ? "public.home.heroCtaPrimaryAuthed"
                    : "public.home.heroCtaPrimary",
                )}
              </LinkButton>
              <LinkButton
                to="/market"
                variant="glass"
                size="lg"
                className="w-full px-8 sm:w-auto"
              >
                {t("public.home.heroCtaSecondary")}
              </LinkButton>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
