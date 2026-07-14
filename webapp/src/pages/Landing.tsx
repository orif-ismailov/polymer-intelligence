/**
 * Landing — the public IMEX AI marketing page (route "/"), built to match
 * docs/desktop_version.jpeg: sticky header (centered nav + stacked Buy/Sell), a hero
 * with the IMEX AI wordmark + 4 feature cards + a network-globe visual, a 4-step
 * "how it works" row, a partner grid, a 5-item feature strip, a barrels final-CTA, and
 * a 4-column footer. Rendered in both contexts; Buy/Sell navigate into the app (the
 * RequireAuth gate prompts Telegram sign-in for anonymous browser visitors).
 *
 * Styled entirely with Tailwind utilities wired to the shared design tokens
 * (src/styles/tokens.css → tailwind.config.ts): `bg-bg`, `bg-surface`, `text-green`,
 * etc. follow the dark/light theme. The only inline styles left are the genuinely
 * dynamic globe-node positions (percentages come from JS). Illustrations (globe,
 * barrels) are CSS/SVG approximations; partner tiles are styled brand names — drop in
 * real logo assets for exact fidelity.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BarChart3,
  Brain,
  Building2,
  Cpu,
  Factory,
  FilePlus2,
  Globe,
  Handshake,
  Headphones,
  Lock,
  Menu,
  MessageCircle,
  Mail,
  Moon,
  ShieldCheck,
  ShoppingCart,
  Store,
  Sun,
  Target,
  Users,
  X,
  Zap,
} from "lucide-react";

import { useScrollReveal } from "../hooks/useScrollReveal";
import { SUPPORTED_LANGS, type Lang } from "../i18n";
import { useTheme } from "../theme/themeStore";

// ── Shared Tailwind class recipes (token-backed) ─────────────────────────────────
const WRAP = "relative z-[1] mx-auto max-w-[1200px] px-5 phone:px-4 desk:px-8";
const SECTION = "py-[34px] phone:py-[26px] desk:py-[46px]";
const PANEL =
  "rounded-[22px] border border-border bg-gradient-to-b from-surface to-surface-2 p-[32px_22px] phone:rounded-[18px] phone:p-[24px_16px] desk:p-[44px_40px]";
const TAG = "mb-2.5 block text-center text-xs font-extrabold uppercase tracking-[0.16em] text-green";
const H2 =
  "mb-2 text-center text-[clamp(22px,5.6vw,26px)] font-extrabold leading-[1.18] tracking-[-0.02em] desk:text-[30px]";
// Scroll reveal: starts hidden, revealed when useScrollReveal sets data-visible.
const REVEAL =
  "translate-y-4 opacity-0 transition-[opacity,transform] duration-500 data-[visible=true]:translate-y-0 data-[visible=true]:opacity-100 motion-reduce:translate-y-0 motion-reduce:opacity-100 motion-reduce:transition-none";
// Base button: no padding/font-size here — each call site adds a size recipe
// (BTN_MD / BTN_LG / BTN_SM) so a single element never carries two conflicting
// padding/font utilities. Labels wrap and center rather than being forced onto one
// no-wrap line, which overflowed narrow screens in longer languages (e.g. uz
// "Xomashyo sotib olish", en "Buy Raw Materials").
const BTN =
  "inline-flex cursor-pointer items-center justify-center gap-[9px] rounded-xl border border-transparent font-bold leading-tight text-center transition-[transform,box-shadow,background] duration-150 active:translate-y-px";
const BTN_PRIMARY =
  "bg-green text-green-on hover:shadow-[0_10px_34px_color-mix(in_srgb,var(--green)_32%,transparent)]";
const BTN_GHOST = "border-border bg-surface text-text hover:bg-surface-2";
const BTN_LG = "px-[26px] py-[15px] text-base";
// Compact size for the sticky mobile bar: two buttons share a narrow row, so trimmed
// padding + a slightly smaller font keep even the longest labels on-screen.
const BTN_SM = "px-3 py-2.5 text-sm";
const FOOTER_LINK =
  "block cursor-pointer py-1.5 text-left text-[13px] text-text-muted transition-colors hover:text-text";
// Partner tile (also reused by the Iran + "…и другие" cells).
const PARTNER_TILE =
  "flex min-h-[66px] items-center justify-center gap-2 rounded-[14px] border border-border bg-bg px-4 py-3 text-center text-[14px] font-extrabold tracking-[0.02em] text-text";

const HERO_CARDS = [
  { key: "f1", Icon: Users },
  { key: "f2", Icon: Factory },
  { key: "f3", Icon: Cpu },
  { key: "f4", Icon: Zap },
] as const;

const STEPS = [
  { key: "s1", Icon: FilePlus2 },
  { key: "s2", Icon: Brain },
  { key: "s3", Icon: Target },
  { key: "s4", Icon: Handshake },
] as const;

// Each partner's `logo` may be EITHER a full URL (e.g. "https://…/lukoil.svg") OR a
// filename served from webapp/public/partners/ (e.g. "lukoil.svg"). Paste the logo
// URL of your choice, or drop a licensed file into public/partners/. Leave it "" and
// the tile falls back to a styled brand name. See public/partners/README.md.
// Only use logos you are permitted to display (real partnership / official brand kit).
// Order matches the reference image (row 1: LUKOIL · SINOPEC · CHINA ENERGY · KunLun ·
// SIBUR; row 2: TURKMENNEBIT · KazMunayGas · NIOC · Uzbekneftegaz · Iran; then "…и другие").
// `logo` may be a URL or a public/partners/<file> name; "" falls back to a styled name.
// The four verified links are Wikimedia Commons (license documented on each file page)
// via Special:FilePath (redirects to the raw SVG). Prefer self-hosting for production.
const PARTNERS = [
  { name: "LUKOIL", logo: "https://commons.wikimedia.org/wiki/Special:FilePath/Lukoil_company_logo.svg" }, // PD-textlogo + trademark
  { name: "SINOPEC", logo: "" }, //  en.wikipedia File:Sinopec.svg (non-free in China)
  { name: "CHINA ENERGY", logo: "" }, // official: ceic.com (no Commons SVG)
  { name: "KunLun", logo: "" }, // official: CNPC brand assets (no Commons SVG)
  { name: "SIBUR", logo: "https://commons.wikimedia.org/wiki/Special:FilePath/Sibur_Holding_Logo.svg" }, // PD-textlogo + trademark
  { name: "TURKMENNEBIT", logo: "" },
  { name: "KazMunayGas", logo: "https://commons.wikimedia.org/wiki/Special:FilePath/KazMunayGas_logo.svg" }, // PD-shape + trademark
  { name: "NIOC", logo: "https://commons.wikimedia.org/wiki/Special:FilePath/National_Iranian_Oil_Company_logo.svg" }, // PD-Iran
  { name: "Uzbekneftegaz", logo: "" }, // official: ung.uz (no Commons SVG)
] as const;

const FEATURES = [
  { key: "f2", Icon: ShieldCheck },
  { key: "f3", Icon: Cpu },
  { key: "f4", Icon: Lock },
  { key: "f5", Icon: Headphones },
] as const;

function LogoMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M5 5 L14 16 L5 27" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M27 5 L18 16 L27 27" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Landing() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const reveal = useScrollReveal<HTMLDivElement>();

  const goBuy = () => navigate("/request/step/1");
  const goSell = () => navigate("/sell");

  // Scroll-aware sticky CTA: hidden until the hero CTAs scroll out of view, and
  // re-hidden once the footer is on screen (so it never covers the footer links).
  const heroCtasRef = useRef<HTMLDivElement>(null);
  const [stickyVisible, setStickyVisible] = useState(false);
  useEffect(() => {
    const heroEl = heroCtasRef.current;
    const footerEl = document.getElementById("footer");
    if (!heroEl) return;
    let heroPassed = false;
    let footerVisible = false;
    const update = () => setStickyVisible(heroPassed && !footerVisible);
    const heroObs = new IntersectionObserver(
      (entries) => {
        const e = entries[0];
        if (!e) return;
        heroPassed = !e.isIntersecting;
        update();
      },
      { threshold: 0 },
    );
    heroObs.observe(heroEl);
    let footerObs: IntersectionObserver | undefined;
    if (footerEl) {
      footerObs = new IntersectionObserver(
        (entries) => {
          const e = entries[0];
          if (!e) return;
          footerVisible = e.isIntersecting;
          update();
        },
        { threshold: 0 },
      );
      footerObs.observe(footerEl);
    }
    return () => {
      heroObs.disconnect();
      footerObs?.disconnect();
    };
  }, []);

  return (
    <div
      ref={reveal}
      className="relative min-h-screen overflow-x-hidden bg-bg text-text antialiased pb-[calc(72px+env(safe-area-inset-bottom))] phone:overflow-x-clip phone:pb-[calc(84px+env(safe-area-inset-bottom))] desk:pb-0 before:pointer-events-none before:absolute before:z-0 before:-top-[140px] before:-right-20 before:h-[620px] before:w-[620px] before:rounded-full before:bg-[radial-gradient(circle,color-mix(in_srgb,var(--green)_16%,transparent),transparent_70%)] before:blur-[110px] before:content-['']"
    >
      <LandingHeader />

      <main className="relative z-[1] mx-auto max-w-[1200px]  phone:overflow-hidden phone:rounded-[20px] phone:py-1">
        {/* ── Hero ─────────────────────────────────────────────────────────── */}
        <section
          className={`${WRAP} pt-[34px] pb-5 phone:pt-[22px] phone:pb-2.5 desk:pt-[56px] desk:pb-[30px]`}
          id="hero"
        >
          <div className="grid grid-cols-1 items-center gap-[30px] phone:gap-5 desk:grid-cols-[1.05fr_0.95fr] desk:gap-10">
            <div data-reveal className={REVEAL}>
              <span className="mb-[18px] inline-flex items-center gap-2 rounded-full border border-green-line bg-green-soft px-3 py-1.5 text-[11px] font-extrabold tracking-[0.12em] text-green">
                <Cpu size={13} /> {t("landing.hero.badge")}
              </span>
              <div className="mb-1 text-[clamp(36px,12vw,46px)] font-black leading-none tracking-[-0.03em] desk:text-[68px]">
                IMEX <span className="text-green">AI</span>
              </div>
              <h1 className="mb-4 text-[clamp(21px,6vw,26px)] font-extrabold leading-[1.15] tracking-[-0.01em] desk:text-[34px]">
                {t("landing.hero.title")}
              </h1>
              <p className="mb-[22px] max-w-[520px] text-[15px] leading-[1.6] text-text-muted phone:mb-[18px]">
                {t("landing.hero.para")}
              </p>

              <div className="mb-[22px] grid grid-cols-2 gap-2.5 phone:grid-cols-1 phone:gap-2">
                {HERO_CARDS.map(({ key, Icon }) => (
                  <div
                    key={key}
                    className="flex items-center gap-2.5 rounded-xl border border-border bg-black/[0.03] p-3 dark:bg-white/[0.025]"
                  >
                    <span className="inline-flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg bg-green-soft text-green">
                      <Icon size={17} />
                    </span>
                    <span className="text-[15px] font-semibold leading-[1.35] text-text">
                      {t(`landing.hero.${key}`)}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mb-4 flex flex-wrap gap-3 phone:flex-col" ref={heroCtasRef}>
                <button className={`${BTN} ${BTN_PRIMARY} ${BTN_LG} phone:w-full`} onClick={goBuy}>
                  <ShoppingCart size={18} /> {t("landing.cta.buy")}
                </button>
                <button className={`${BTN} ${BTN_GHOST} ${BTN_LG} phone:w-full`} onClick={goSell}>
                  <Store size={18} /> {t("landing.cta.sell")}
                </button>
              </div>
              <span className="inline-flex items-center gap-2 text-[13px] text-text-muted [&_svg]:text-green">
                <ShieldCheck size={15} /> {t("landing.hero.trust")}
              </span>
            </div>

            <div data-reveal className={REVEAL}>
              <AiVisual />
            </div>
          </div>
        </section>

        {/* ── How it works ─────────────────────────────────────────────────── */}
        <section className={`${WRAP} ${SECTION}`} id="how">
          <div className={PANEL} data-reveal>
            <span className={TAG}>{t("landing.how.tag")}</span>
            <h2 className={H2}>{t("landing.how.title")}</h2>
            <div className="mt-[26px] grid grid-cols-1 gap-[22px] desk:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] desk:items-start desk:gap-2">
              {STEPS.map(({ key, Icon }, i) => (
                <StepWithArrow key={key} last={i === STEPS.length - 1} num={i + 1} Icon={Icon} keyName={key} />
              ))}
            </div>
          </div>
        </section>

        {/* ── Partners ─────────────────────────────────────────────────────── */}
        <section className={`${WRAP} ${SECTION}`} id="partners">
          <div className={PANEL} data-reveal>
            <span className={TAG}>{t("landing.partners.tag")}</span>
            <h2 className={H2}>{t("landing.partners.title")}</h2>
            <div className="mt-6 grid grid-cols-2 gap-3 desk:grid-cols-5">
              {PARTNERS.map((p) => (
                <PartnerTile key={p.name} name={p.name} logo={p.logo} />
              ))}
              <span className={PARTNER_TILE}>
                <span className="flex-none text-[18px] leading-none" aria-hidden="true">
                  🇮🇷
                </span>{" "}
                {t("landing.partners.iran")}
              </span>
              <span className={`${PARTNER_TILE} col-[1/-1] text-xs font-semibold text-text-muted`}>
                {t("landing.partners.other")}
              </span>
            </div>
          </div>
        </section>

        {/* ── Feature strip ────────────────────────────────────────────────── */}
        <section className={`${WRAP} ${SECTION}`} id="why">
          <div className={PANEL} data-reveal>
            <div className="grid grid-cols-1 gap-5 desk:grid-cols-5 desk:gap-2">
              <div className="flex items-center gap-3 text-left desk:flex-col desk:gap-2.5 desk:border-l desk:border-border desk:px-3.5 desk:text-center desk:first:border-l-0">
                <span className="inline-flex h-[44px] w-[44px] flex-none items-center justify-center rounded-xl bg-green-soft text-green">
                  <Users size={20} />
                </span>
                <span className="whitespace-nowrap text-[22px] font-black leading-none text-green">
                  {t("landing.features.count")}
                </span>
                <span className="text-[13px] font-semibold leading-[1.4] text-text desk:text-center">
                  {t("landing.features.f1")}
                </span>
              </div>
              {FEATURES.map(({ key, Icon }) => (
                <div
                  key={key}
                  className="flex items-center gap-3 text-left desk:flex-col desk:gap-2.5 desk:border-l desk:border-border desk:px-3.5 desk:text-center desk:first:border-l-0"
                >
                  <span className="inline-flex h-[44px] w-[44px] flex-none items-center justify-center rounded-xl bg-green-soft text-green">
                    <Icon size={20} />
                  </span>
                  <span className="text-[13px] font-semibold leading-[1.4] text-text desk:text-center">
                    {t(`landing.features.${key}`)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Final CTA ────────────────────────────────────────────────────── */}
        <section className={`${WRAP} ${SECTION}`}>
          <div className={`${PANEL} grid grid-cols-1 items-center gap-6 desk:grid-cols-[0.8fr_1.2fr]`} data-reveal>
            <div className="flex min-h-[150px] items-center justify-center">
              <CtaArt />
            </div>
            <div className="desk:flex desk:flex-wrap desk:items-center desk:justify-between desk:gap-6">
              <div>
                <h2 className="mb-2 text-[clamp(21px,5.4vw,24px)] font-extrabold leading-[1.15]">
                  {t("landing.final.title")}
                </h2>
                <p className="mb-[18px] text-[15px] leading-[1.55] text-text-muted">{t("landing.final.subtitle")}</p>
              </div>
              <div className="flex flex-wrap gap-3 phone:flex-col desk:flex-shrink-0">
                <button className={`${BTN} ${BTN_PRIMARY} ${BTN_LG} phone:w-full`} onClick={goBuy}>
                  <ShoppingCart size={18} /> {t("landing.cta.buy")}
                </button>
                <button className={`${BTN} ${BTN_GHOST} ${BTN_LG} phone:w-full`} onClick={goSell}>
                  <Store size={18} /> {t("landing.cta.sell")}
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>

      <LandingFooter />

      {/* Sticky mobile CTA — shown only after the hero CTAs scroll off (see effect) */}
      <div
        className={`fixed inset-x-0 bottom-0 z-[60] flex gap-2.5 border-t border-border bg-[color-mix(in_srgb,var(--bg)_90%,transparent)] px-4 pt-2.5 pb-[calc(10px+env(safe-area-inset-bottom))] backdrop-blur-[12px] transition-transform duration-300 will-change-transform motion-reduce:transition-none desk:hidden ${
          stickyVisible ? "translate-y-0" : "translate-y-[120%]"
        }`}
      >
        <button className={`${BTN} ${BTN_PRIMARY} ${BTN_SM} min-w-0 flex-1`} onClick={goBuy}>
          <ShoppingCart size={17} className="flex-none" /> {t("landing.cta.buy")}
        </button>
        <button className={`${BTN} ${BTN_GHOST} ${BTN_SM} min-w-0 flex-1`} onClick={goSell}>
          <Store size={17} className="flex-none" /> {t("landing.cta.sell")}
        </button>
      </div>
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────────────────────────

function LandingHeader() {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  // "about" → hero (page top): it and "how" previously both pointed at #how.
  const NAV = [
    { key: "about", id: "hero" },
    { key: "how", id: "how" },
    { key: "why", id: "why" },
    { key: "partners", id: "partners" },
    { key: "contacts", id: "footer" },
  ];
  const go = (id: string) => {
    setMenuOpen(false);
    scrollTo(id);
  };
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-[color-mix(in_srgb,var(--bg)_80%,transparent)] backdrop-blur-[14px]">
      <div className="mx-auto flex h-[68px] max-w-[1200px] items-center gap-3.5 px-5">
        <button
          className="inline-flex flex-none cursor-pointer items-center gap-2.5 p-0 text-xl font-extrabold tracking-[-0.01em] text-text"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          <LogoMark className="h-[30px] w-[30px] text-green drop-shadow-[0_0_8px_color-mix(in_srgb,var(--green)_50%,transparent)]" />
          IMEX <span className="text-green">AI</span>
        </button>
        <nav className="mx-auto hidden items-center gap-0.5 desk:flex">
          {NAV.map((n) => (
            <button
              key={n.key}
              className="cursor-pointer rounded-lg px-3 py-2 text-sm font-medium text-text-muted transition-colors hover:text-text"
              onClick={() => scrollTo(n.id)}
            >
              {t(`landing.nav.${n.key}`)}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2.5">
          <ThemeToggle />
          <LangMenu />
          <button
            className="inline-flex h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-[10px] border border-border bg-surface text-text desk:hidden"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label="Menu"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
      {menuOpen && (
        <>
          <div className="fixed inset-0 z-[54] desk:hidden" onClick={() => setMenuOpen(false)} aria-hidden="true" />
          <nav
            className="absolute inset-x-0 top-full z-[55] flex flex-col gap-0.5 border-b border-border bg-surface-2 p-2 shadow-[0_18px_40px_rgba(0,0,0,0.5)] desk:hidden"
            role="menu"
          >
            {NAV.map((n) => (
              <button
                key={n.key}
                role="menuitem"
                className="cursor-pointer rounded-[10px] p-3 text-left text-[15px] font-medium text-text-muted transition-colors hover:bg-black/5 hover:text-text dark:hover:bg-white/5"
                onClick={() => go(n.id)}
              >
                {t(`landing.nav.${n.key}`)}
              </button>
            ))}
          </nav>
        </>
      )}
    </header>
  );
}

// Final-CTA image. Self-hosted polymer photo from webapp/public/ (resolved via
// import.meta.env.BASE_URL below). Swap it by dropping another file into public/ and
// updating this name, or paste a full https URL. If the source is missing the CSS
// barrels illustration is shown instead.
const CTA_IMAGE = "polymer_image.jpeg";

function CtaArt() {
  const [broken, setBroken] = useState(false);
  const src = /^https?:\/\//.test(CTA_IMAGE)
    ? CTA_IMAGE
    : CTA_IMAGE
      ? `${import.meta.env.BASE_URL}${CTA_IMAGE}`
      : "";

  if (src && !broken) {
    return (
      <img
        className="block max-h-[240px] w-full rounded-2xl border border-border object-cover"
        src={src}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
      />
    );
  }

  // Fallback: CSS barrels illustration (approximates the reference render). Barrel
  // greys are decorative (not brand tokens); the neon hoop lines use the token green.
  const barrel =
    "relative w-[44px] rounded-[8px/14px] border border-white/[0.08] bg-[linear-gradient(90deg,#0c1016_0%,#1a2230_45%,#0c1016_100%)] shadow-[0_10px_24px_rgba(0,0,0,0.5)] before:absolute before:inset-x-0 before:top-[22px] before:h-[3px] before:bg-green before:opacity-55 before:shadow-[0_0_8px_color-mix(in_srgb,var(--green)_60%,transparent)] before:content-[''] after:absolute after:inset-x-0 after:bottom-[22px] after:h-[3px] after:bg-green after:opacity-55 after:shadow-[0_0_8px_color-mix(in_srgb,var(--green)_60%,transparent)] after:content-['']";
  return (
    <div className="flex h-[120px] items-end gap-2" aria-hidden="true">
      <span className={`${barrel} h-[84px]`} />
      <span className={`${barrel} h-[104px]`} />
      <span className={`${barrel} h-[84px]`} />
      <span className={`${barrel} h-[104px]`} />
      <span className={`${barrel} h-[84px]`} />
    </div>
  );
}

function PartnerTile({ name, logo }: { name: string; logo: string }) {
  const [broken, setBroken] = useState(false);
  // A full URL is used as-is; a bare filename resolves to public/partners/<file>.
  const src = /^https?:\/\//.test(logo) ? logo : logo ? `${import.meta.env.BASE_URL}partners/${logo}` : "";
  const showText = broken || !src;
  return (
    <span className={`${PARTNER_TILE} [&_svg]:flex-none [&_svg]:text-green`} title={name}>
      {showText ? (
        <>
          <Factory size={15} /> {name}
        </>
      ) : (
        <img
          className="block max-h-[36px] max-w-[86%] object-contain"
          src={src}
          alt={name}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
        />
      )}
    </span>
  );
}

// Light/dark toggle for the public landing (Profile's theme switch is behind auth).
// Flips the resolved scheme; the choice persists via the shared theme store.
function ThemeToggle() {
  const { t } = useTranslation();
  const { scheme, setPref } = useTheme();
  const isDark = scheme === "dark";
  return (
    <button
      className="inline-flex h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-[10px] border border-border bg-surface text-text"
      onClick={() => setPref(isDark ? "light" : "dark")}
      aria-label={isDark ? t("settings.themeOpt.light") : t("settings.themeOpt.dark")}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

function LangMenu() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const current: Lang = (SUPPORTED_LANGS as readonly string[]).includes(i18n.language) ? (i18n.language as Lang) : "ru";
  const choose = (lang: Lang) => {
    setOpen(false);
    if (lang !== current) void i18n.changeLanguage(lang);
  };
  return (
    <div className="relative">
      <button
        className="inline-flex h-[38px] cursor-pointer items-center gap-[7px] rounded-[10px] border border-border bg-surface px-3 text-[13px] font-semibold text-text"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Globe size={15} /> {current.toUpperCase()}
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} className="fixed inset-0 z-[60]" aria-hidden="true" />
          <ul className="absolute right-0 top-[calc(100%+8px)] z-[61] m-0 min-w-[150px] list-none rounded-xl border border-border bg-surface-2 p-1.5">
            {SUPPORTED_LANGS.map((l) => (
              <li key={l}>
                <button
                  className="block w-full cursor-pointer rounded-lg px-2.5 py-[9px] text-left text-sm text-text aria-selected:bg-black/[0.06] aria-selected:font-bold dark:aria-selected:bg-white/[0.06]"
                  role="option"
                  aria-selected={l === current}
                  onClick={() => choose(l)}
                >
                  {t(`settings.lang.${l}`)}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

// ── How-it-works step (+ desktop arrow) ─────────────────────────────────────────

function StepWithArrow({
  num,
  Icon,
  keyName,
  last,
}: {
  num: number;
  Icon: typeof Brain;
  keyName: string;
  last: boolean;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className={`relative text-center ${REVEAL}`} data-reveal>
        <span className="mb-3.5 inline-flex h-[66px] w-[66px] items-center justify-center rounded-full border border-green-line bg-green-soft text-green">
          <Icon size={26} />
        </span>
        <h3 className="mb-2 text-[15px] font-bold">
          <b className="font-extrabold text-green">{num}.</b> {t(`landing.how.${keyName}.title`)}
        </h3>
        <p className="mx-auto max-w-[min(320px,82%)] text-[13px] leading-[1.5] text-text-muted">
          {t(`landing.how.${keyName}.desc`)}
        </p>
      </div>
      {!last && (
        <div
          className="hidden text-green desk:flex desk:items-center desk:justify-center desk:pt-[22px]"
          aria-hidden="true"
        >
          <ArrowGlyph />
        </div>
      )}
    </>
  );
}

function ArrowGlyph() {
  return (
    <svg width="40" height="16" viewBox="0 0 40 16" fill="none">
      <path d="M0 8 H34 M28 2 L34 8 L28 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Hero network globe ──────────────────────────────────────────────────────────

function AiVisual() {
  const { t } = useTranslation();
  const nodes = [
    { key: "suppliers", Icon: Factory, left: "27%", top: "23%" },
    { key: "buyers", Icon: Building2, left: "73%", top: "23%" },
    { key: "analysis", Icon: BarChart3, left: "18%", top: "63%" },
    { key: "deals", Icon: Handshake, left: "82%", top: "63%" },
  ] as const;

  return (
    <div className="relative mx-auto aspect-square w-full max-w-[460px] phone:max-w-[300px]" aria-hidden="true">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 400" fill="none">
        <defs>
          <radialGradient id="imexSphere" cx="50%" cy="45%" r="55%">
            <stop offset="0%" stopColor="var(--green)" stopOpacity={0.22} />
            <stop offset="60%" stopColor="var(--green)" stopOpacity={0.05} />
            <stop offset="100%" stopColor="var(--green)" stopOpacity={0} />
          </radialGradient>
          <radialGradient id="imexBase" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--green)" stopOpacity={0.5} />
            <stop offset="100%" stopColor="var(--green)" stopOpacity={0} />
          </radialGradient>
        </defs>
        {/* sphere */}
        <circle cx="200" cy="205" r="120" fill="url(#imexSphere)" />
        <circle cx="200" cy="205" r="120" stroke="var(--green)" strokeOpacity={0.18} strokeWidth="1" />
        <ellipse cx="200" cy="205" rx="120" ry="46" stroke="var(--green)" strokeOpacity={0.14} strokeWidth="1" />
        <ellipse cx="200" cy="205" rx="60" ry="120" stroke="var(--green)" strokeOpacity={0.1} strokeWidth="1" />
        {/* connecting lines from center to nodes */}
        {[
          [108, 92],
          [292, 92],
          [72, 252],
          [328, 252],
        ].map(([x, y], i) => (
          <g key={i}>
            <line x1="200" y1="205" x2={x} y2={y} stroke="var(--green)" strokeOpacity={0.35} strokeWidth="1.2" />
            <circle cx={x} cy={y} r="3.5" fill="var(--green)" />
          </g>
        ))}
        {/* glowing base */}
        <ellipse cx="200" cy="352" rx="130" ry="26" fill="url(#imexBase)" />
      </svg>

      {nodes.map(({ key, Icon, left, top }) => (
        <div
          key={key}
          className="absolute flex w-[118px] -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1.5 text-center phone:w-[88px] phone:gap-1"
          style={{ left, top }}
        >
          <span className="inline-flex h-[46px] w-[46px] items-center justify-center rounded-full border border-green-line bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] text-green shadow-[0_0_22px_color-mix(in_srgb,var(--green)_25%,transparent)] phone:h-[40px] phone:w-[40px]">
            <Icon size={20} />
          </span>
          <span className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[11px] font-semibold leading-[1.25] text-text-muted">
            {t(`landing.hero.node.${key}`)}
          </span>
        </div>
      ))}

      <div className="absolute left-1/2 top-1/2 flex h-[74px] w-[74px] -translate-x-1/2 -translate-y-1/2 animate-pulse-glow items-center justify-center rounded-[18px] bg-green text-2xl font-black text-green-on shadow-[0_0_46px_color-mix(in_srgb,var(--green)_60%,transparent)] motion-reduce:animate-none phone:h-[60px] phone:w-[60px] phone:rounded-[15px] phone:text-xl">
        AI
      </div>
    </div>
  );
}

// ── Footer ─────────────────────────────────────────────────────────────────────

function LandingFooter() {
  const { t } = useTranslation();
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <footer className="mt-[28px] border-t border-border pt-[34px]" id="footer">
      <div className={WRAP}>
        <div className="grid grid-cols-1 gap-[26px] desk:grid-cols-[1.6fr_1fr_1fr_1.2fr] desk:gap-8">
          <div>
            <span className="inline-flex items-center gap-2 text-[18px] font-extrabold">
              <LogoMark className="h-[30px] w-[30px] text-green drop-shadow-[0_0_8px_color-mix(in_srgb,var(--green)_50%,transparent)]" />
              IMEX <span className="text-green">AI</span>
            </span>
            <p className="mt-3 max-w-[320px] text-[13px] leading-[1.55] text-text-muted">
              {t("landing.footer.tagline")}
            </p>
          </div>
          <div>
            <h4 className="mb-3 text-[13px] font-bold text-text">{t("landing.footer.colPlatform")}</h4>
            <button className={FOOTER_LINK} onClick={() => scrollTo("how")}>
              {t("landing.nav.about")}
            </button>
            <button className={FOOTER_LINK} onClick={() => scrollTo("how")}>
              {t("landing.nav.how")}
            </button>
            <button className={FOOTER_LINK} onClick={() => scrollTo("why")}>
              {t("landing.nav.why")}
            </button>
          </div>
          <div>
            <h4 className="mb-3 text-[13px] font-bold text-text">{t("landing.footer.colCompany")}</h4>
            <button className={FOOTER_LINK} onClick={() => scrollTo("partners")}>
              {t("landing.nav.partners")}
            </button>
            <button className={FOOTER_LINK} onClick={() => scrollTo("footer")}>
              {t("landing.nav.contacts")}
            </button>
          </div>
          <div>
            <h4 className="mb-3 text-[13px] font-bold text-text">{t("landing.footer.colSupport")}</h4>
            <span className="flex items-center gap-2 py-1.5 text-[13px] text-text-muted [&_svg]:text-green">
              <Mail size={15} /> info@imex-ai.com
            </span>
            <span className="flex items-center gap-2 py-1.5 text-[13px] text-text-muted [&_svg]:text-green">
              <MessageCircle size={15} /> @imex_ai_support
            </span>
            <button className={FOOTER_LINK} onClick={() => scrollTo("how")}>
              {t("landing.footer.faq")}
            </button>
            <button
              className={FOOTER_LINK}
              onClick={() => window.open("https://t.me/imex_ai_support", "_blank", "noopener")}
            >
              {t("landing.footer.support24")}
            </button>
          </div>
        </div>
        <div className="mt-[26px] flex flex-col gap-2 border-t border-border py-5 text-xs text-text-muted desk:flex-row desk:items-center desk:justify-between">
          <span>{t("landing.footer.rights")}</span>
          <div className="flex flex-wrap gap-[18px]">
            <button className="cursor-pointer p-0 text-xs text-text-muted transition-colors hover:text-text">
              {t("landing.footer.privacy")}
            </button>
            <button className="cursor-pointer p-0 text-xs text-text-muted transition-colors hover:text-text">
              {t("landing.footer.terms")}
            </button>
          </div>
        </div>
      </div>
    </footer>
  );
}
