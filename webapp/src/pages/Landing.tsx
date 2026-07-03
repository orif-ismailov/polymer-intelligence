/**
 * Landing — the public IMEX AI marketing page (route "/"), built to match
 * docs/desktop_version.jpeg: sticky header (centered nav + stacked Buy/Sell), a hero
 * with the IMEX AI wordmark + 4 feature cards + a network-globe visual, a 4-step
 * "how it works" row, a partner grid, a 5-item feature strip, a barrels final-CTA, and
 * a 4-column footer. Rendered in both contexts; Buy/Sell navigate into the app (the
 * RequireAuth gate prompts Telegram sign-in for anonymous browser visitors).
 *
 * Scoped to landing.css. Illustrations (globe, barrels) are CSS/SVG approximations;
 * partner tiles are styled brand names — drop in real logo assets for exact fidelity.
 */

import { useState } from "react";
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
  MessageCircle,
  Mail,
  ShieldCheck,
  ShoppingCart,
  Store,
  Target,
  Users,
  Zap,
} from "lucide-react";

import { useScrollReveal } from "../hooks/useScrollReveal";
import { SUPPORTED_LANGS, type Lang } from "../i18n";
import "../styles/landing.css";

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

  return (
    <div className="imex-landing" ref={reveal}>
      <LandingHeader />

      <main className="imex-main">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="imex-wrap imex-hero">
        <div className="imex-hero__grid">
          <div data-reveal className="reveal">
            <span className="imex-hero__badge">
              <Cpu size={13} /> {t("landing.hero.badge")}
            </span>
            <div className="imex-hero__wordmark">
              IMEX <span className="imex-accent">AI</span>
            </div>
            <h1 className="imex-hero__title">{t("landing.hero.title")}</h1>
            <p className="imex-hero__para">{t("landing.hero.para")}</p>

            <div className="imex-hero__cards">
              {HERO_CARDS.map(({ key, Icon }) => (
                <div key={key} className="imex-fcard">
                  <span className="imex-fcard__icon">
                    <Icon size={17} />
                  </span>
                  <span className="imex-fcard__text">{t(`landing.hero.${key}`)}</span>
                </div>
              ))}
            </div>

            <div className="imex-hero__ctas">
              <button className="imex-btn imex-btn--primary imex-btn--lg" onClick={goBuy}>
                <ShoppingCart size={18} /> {t("landing.cta.buy")}
              </button>
              <button className="imex-btn imex-btn--ghost imex-btn--lg" onClick={goSell}>
                <Store size={18} /> {t("landing.cta.sell")}
              </button>
            </div>
            <span className="imex-hero__trust">
              <ShieldCheck size={15} /> {t("landing.hero.trust")}
            </span>
          </div>

          <div data-reveal className="reveal">
            <AiVisual />
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="imex-wrap imex-section" id="how">
        <div className="imex-panel" data-reveal>
          <span className="imex-tag">{t("landing.how.tag")}</span>
          <h2 className="imex-h2">{t("landing.how.title")}</h2>
          <div className="imex-steps">
            {STEPS.map(({ key, Icon }, i) => (
              <StepWithArrow key={key} last={i === STEPS.length - 1} num={i + 1} Icon={Icon} keyName={key} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Partners ─────────────────────────────────────────────────────── */}
      <section className="imex-wrap imex-section" id="partners">
        <div className="imex-panel" data-reveal>
          <span className="imex-tag">{t("landing.partners.tag")}</span>
          <h2 className="imex-h2">{t("landing.partners.title")}</h2>
          <div className="imex-partners">
            {PARTNERS.map((p) => (
              <PartnerTile key={p.name} name={p.name} logo={p.logo} />
            ))}
            <span className="imex-partner">
              <span className="imex-partner__flag" aria-hidden="true">🇮🇷</span> {t("landing.partners.iran")}
            </span>
            <span className="imex-partner imex-partner--muted" style={{ gridColumn: "1 / -1" }}>
              {t("landing.partners.other")}
            </span>
          </div>
        </div>
      </section>

      {/* ── Feature strip ────────────────────────────────────────────────── */}
      <section className="imex-wrap imex-section" id="why">
        <div className="imex-panel" data-reveal>
          <div className="imex-strip">
            <div className="imex-feat">
              <span className="imex-feat__icon">
                <Users size={20} />
              </span>
              <span className="imex-feat__count">{t("landing.features.count")}</span>
              <span className="imex-feat__text">{t("landing.features.f1")}</span>
            </div>
            {FEATURES.map(({ key, Icon }) => (
              <div key={key} className="imex-feat">
                <span className="imex-feat__icon">
                  <Icon size={20} />
                </span>
                <span className="imex-feat__text">{t(`landing.features.${key}`)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="imex-wrap imex-section">
        <div className="imex-panel imex-final" data-reveal>
          <div className="imex-final__art">
            <CtaArt />
          </div>
          <div className="imex-final__body">
            <div>
              <h2 className="imex-final__title">{t("landing.final.title")}</h2>
              <p className="imex-final__sub">{t("landing.final.subtitle")}</p>
            </div>
            <div className="imex-final__ctas">
              <button className="imex-btn imex-btn--primary imex-btn--lg" onClick={goBuy}>
                <ShoppingCart size={18} /> {t("landing.cta.buy")}
              </button>
              <button className="imex-btn imex-btn--ghost imex-btn--lg" onClick={goSell}>
                <Store size={18} /> {t("landing.cta.sell")}
              </button>
            </div>
          </div>
        </div>
      </section>
      </main>

      <LandingFooter />

      {/* Sticky mobile CTA */}
      <div className="imex-sticky-cta">
        <button className="imex-btn imex-btn--primary" onClick={goBuy}>
          <ShoppingCart size={17} /> {t("landing.cta.buy")}
        </button>
        <button className="imex-btn imex-btn--ghost" onClick={goSell}>
          <Store size={17} /> {t("landing.cta.sell")}
        </button>
      </div>
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────────────────────────

function LandingHeader() {
  const { t } = useTranslation();
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const NAV = [
    { key: "about", id: "how" },
    { key: "how", id: "how" },
    { key: "why", id: "why" },
    { key: "partners", id: "partners" },
    { key: "contacts", id: "footer" },
  ];
  return (
    <header className="imex-lh">
      <div className="imex-lh__row">
        <button className="imex-brand" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
          <LogoMark className="imex-brand__logo" />
          IMEX <span className="imex-accent">AI</span>
        </button>
        <nav className="imex-lh__nav">
          {NAV.map((n) => (
            <button key={n.key} className="imex-lh__link" onClick={() => scrollTo(n.id)}>
              {t(`landing.nav.${n.key}`)}
            </button>
          ))}
        </nav>
        <div className="imex-lh__actions">
          <LangMenu />
        </div>
      </div>
    </header>
  );
}

// Final-CTA image. Currently a free-licensed Unsplash photo (Unsplash License:
// commercial use, no attribution required) of polymer granules — on brand. Swap it by
// pasting another URL, or self-host: drop a file at webapp/public/cta/deal.jpg and set
// CTA_IMAGE = "cta/deal.jpg". While the source is missing the CSS barrels are shown.
// Source: https://unsplash.com/photos/colored-granular-substance-is-scattered-on-a-surface-yB5BPsckr-s
const CTA_IMAGE =
  "https://images.unsplash.com/photo-1751629663077-67876b0fb818?auto=format&fit=crop&w=1200&q=70";

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
        className="imex-final__img"
        src={src}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
      />
    );
  }

  // Fallback: CSS barrels illustration (approximates the reference render).
  return (
    <div className="imex-barrels" aria-hidden="true">
      <span className="imex-barrel" />
      <span className="imex-barrel imex-barrel--tall" />
      <span className="imex-barrel" />
      <span className="imex-barrel imex-barrel--tall" />
      <span className="imex-barrel" />
    </div>
  );
}

function PartnerTile({ name, logo }: { name: string; logo: string }) {
  const [broken, setBroken] = useState(false);
  // A full URL is used as-is; a bare filename resolves to public/partners/<file>.
  const src = /^https?:\/\//.test(logo) ? logo : logo ? `${import.meta.env.BASE_URL}partners/${logo}` : "";
  const showText = broken || !src;
  return (
    <span className="imex-partner" title={name}>
      {showText ? (
        <>
          <Factory size={15} /> {name}
        </>
      ) : (
        <img
          className="imex-partner__logo"
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

function LangMenu() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const current: Lang = (SUPPORTED_LANGS as readonly string[]).includes(i18n.language) ? (i18n.language as Lang) : "ru";
  const choose = (lang: Lang) => {
    setOpen(false);
    if (lang !== current) void i18n.changeLanguage(lang);
  };
  return (
    <div className="imex-lang">
      <button className="imex-lang__btn" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}>
        <Globe size={15} /> {current.toUpperCase()}
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 60 }} aria-hidden="true" />
          <ul className="imex-lang__menu" role="listbox">
            {SUPPORTED_LANGS.map((l) => (
              <li key={l}>
                <button className="imex-lang__opt" role="option" aria-selected={l === current} onClick={() => choose(l)}>
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
      <div className="imex-step" data-reveal>
        <span className="imex-step__icon">
          <Icon size={26} />
        </span>
        <h3 className="imex-step__title">
          <b>{num}.</b> {t(`landing.how.${keyName}.title`)}
        </h3>
        <p className="imex-step__desc">{t(`landing.how.${keyName}.desc`)}</p>
      </div>
      {!last && (
        <div className="imex-step__arrow" aria-hidden="true">
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
    <div className="imex-viz" aria-hidden="true">
      <svg className="imex-viz__svg" viewBox="0 0 400 400" fill="none">
        <defs>
          <radialGradient id="imexSphere" cx="50%" cy="45%" r="55%">
            <stop offset="0%" stopColor="rgba(92,255,110,0.22)" />
            <stop offset="60%" stopColor="rgba(92,255,110,0.05)" />
            <stop offset="100%" stopColor="rgba(92,255,110,0)" />
          </radialGradient>
          <radialGradient id="imexBase" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(92,255,110,0.5)" />
            <stop offset="100%" stopColor="rgba(92,255,110,0)" />
          </radialGradient>
        </defs>
        {/* sphere */}
        <circle cx="200" cy="205" r="120" fill="url(#imexSphere)" />
        <circle cx="200" cy="205" r="120" stroke="rgba(92,255,110,0.18)" strokeWidth="1" />
        <ellipse cx="200" cy="205" rx="120" ry="46" stroke="rgba(92,255,110,0.14)" strokeWidth="1" />
        <ellipse cx="200" cy="205" rx="60" ry="120" stroke="rgba(92,255,110,0.1)" strokeWidth="1" />
        {/* connecting lines from center to nodes */}
        {[
          [108, 92],
          [292, 92],
          [72, 252],
          [328, 252],
        ].map(([x, y], i) => (
          <g key={i}>
            <line x1="200" y1="205" x2={x} y2={y} stroke="rgba(92,255,110,0.35)" strokeWidth="1.2" />
            <circle cx={x} cy={y} r="3.5" fill="#5cff6e" />
          </g>
        ))}
        {/* glowing base */}
        <ellipse cx="200" cy="352" rx="130" ry="26" fill="url(#imexBase)" />
      </svg>

      {nodes.map(({ key, Icon, left, top }) => (
        <div key={key} className="imex-node" style={{ left, top }}>
          <span className="imex-node__badge">
            <Icon size={20} />
          </span>
          <span className="imex-node__label">{t(`landing.hero.node.${key}`)}</span>
        </div>
      ))}

      <div className="imex-viz__core">AI</div>
    </div>
  );
}

// ── Footer ─────────────────────────────────────────────────────────────────────

function LandingFooter() {
  const { t } = useTranslation();
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <footer className="imex-footer" id="footer">
      <div className="imex-wrap">
        <div className="imex-footer__grid">
          <div>
            <span className="imex-footer__brand">
              <LogoMark className="imex-brand__logo" />
              IMEX <span className="imex-accent">AI</span>
            </span>
            <p className="imex-footer__tag">{t("landing.footer.tagline")}</p>
          </div>
          <div className="imex-footer__col">
            <h4>{t("landing.footer.colPlatform")}</h4>
            <button onClick={() => scrollTo("how")}>{t("landing.nav.about")}</button>
            <button onClick={() => scrollTo("how")}>{t("landing.nav.how")}</button>
            <button onClick={() => scrollTo("why")}>{t("landing.nav.why")}</button>
          </div>
          <div className="imex-footer__col">
            <h4>{t("landing.footer.colCompany")}</h4>
            <button onClick={() => scrollTo("partners")}>{t("landing.nav.partners")}</button>
            <button onClick={() => scrollTo("footer")}>{t("landing.nav.contacts")}</button>
          </div>
          <div className="imex-footer__col">
            <h4>{t("landing.footer.colSupport")}</h4>
            <span className="imex-footer__contact">
              <Mail size={15} /> info@imex-ai.com
            </span>
            <span className="imex-footer__contact">
              <MessageCircle size={15} /> @imex_ai_support
            </span>
            <button>{t("landing.footer.faq")}</button>
            <button>{t("landing.footer.support24")}</button>
          </div>
        </div>
        <div className="imex-footer__bar">
          <span>{t("landing.footer.rights")}</span>
          <div className="imex-footer__legal">
            <button>{t("landing.footer.privacy")}</button>
            <button>{t("landing.footer.terms")}</button>
          </div>
        </div>
      </div>
    </footer>
  );
}
