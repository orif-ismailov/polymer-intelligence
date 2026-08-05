import { createContext } from "react";

/**
 * The head manager's context and serialization, kept in a sibling `.ts`.
 *
 * Same reason `tabStyles.ts` sits beside `Tabs.tsx` (design-system.md P4):
 * exporting a helper next to a component from a `.tsx` trips
 * `react-refresh/only-export-components`, and the lint gate runs at
 * `--max-warnings 0`.
 */

export interface SeoData {
  title?: string;
  description?: string;
  /** Absolute canonical URL. Built by the caller from the public site origin. */
  canonical?: string;
  /** `hreflang` alternates, keyed by language code. */
  alternates?: Record<string, string>;
  ogType?: string;
  ogImage?: string;
  /** Keep this page out of the index (the cabinet, filtered result pages). */
  noindex?: boolean;
  /** JSON-LD documents emitted as `<script type="application/ld+json">`. */
  jsonLd?: Array<Record<string, unknown>>;
}

/** Mutable sink the server render writes into; null in the browser. */
export interface HeadSink {
  current: SeoData;
}

export const HeadContext = createContext<HeadSink | null>(null);

export function createHeadSink(): HeadSink {
  return { current: {} };
}

/** Marks every element this manager owns, so a client update can replace them. */
export const MANAGED = "data-seo-managed";

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * JSON-LD goes inside a `<script>`, where the escaping rules differ: the only
 * sequence that can break out is `</script`, and HTML-escaping the whole
 * document would corrupt the JSON. Escape `<` plus the two line separators that
 * are legal in JSON but not in JavaScript source.
 */
export function escapeJsonLd(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

/** Patch `document.head` after a client-side navigation. */
export function applyHeadToDocument(data: SeoData): void {
  if (data.title) document.title = data.title;

  for (const el of Array.from(document.querySelectorAll(`[${MANAGED}]`))) {
    el.remove();
  }

  const head = document.head;
  const add = (tag: string, attrs: Record<string, string>): void => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    el.setAttribute(MANAGED, "");
    head.appendChild(el);
  };

  if (data.description) {
    // The static description in index.html is not ours, so it would survive
    // alongside a route's own. Drop it before writing.
    document.querySelector('meta[name="description"]:not([data-seo-managed])')?.remove();
    add("meta", { name: "description", content: data.description });
  }
  if (data.canonical) add("link", { rel: "canonical", href: data.canonical });
  for (const [lang, href] of Object.entries(data.alternates ?? {})) {
    add("link", { rel: "alternate", hreflang: lang, href });
  }
  if (data.noindex) add("meta", { name: "robots", content: "noindex,nofollow" });
  add("meta", { property: "og:type", content: data.ogType ?? "website" });
  if (data.title) add("meta", { property: "og:title", content: data.title });
  if (data.description) {
    add("meta", { property: "og:description", content: data.description });
  }
  if (data.canonical) add("meta", { property: "og:url", content: data.canonical });
  if (data.ogImage) add("meta", { property: "og:image", content: data.ogImage });

  for (const doc of data.jsonLd ?? []) {
    const el = document.createElement("script");
    el.setAttribute("type", "application/ld+json");
    el.setAttribute(MANAGED, "");
    el.textContent = escapeJsonLd(doc);
    head.appendChild(el);
  }
}

/**
 * Serialize the collected head into an HTML string for the server template.
 *
 * Emits `<title>` too, so the template's placeholder is replaced wholesale
 * rather than the server merging two sources of truth for the title.
 */
export function renderHeadTags(data: SeoData): string {
  const out: string[] = [];
  if (data.title) out.push(`<title>${escapeAttr(data.title)}</title>`);
  if (data.description) {
    out.push(`<meta name="description" content="${escapeAttr(data.description)}" />`);
  }
  if (data.canonical) {
    out.push(`<link rel="canonical" href="${escapeAttr(data.canonical)}" />`);
  }
  for (const [lang, href] of Object.entries(data.alternates ?? {})) {
    out.push(
      `<link rel="alternate" hreflang="${escapeAttr(lang)}" href="${escapeAttr(href)}" />`,
    );
  }
  if (data.noindex) out.push(`<meta name="robots" content="noindex,nofollow" />`);
  out.push(`<meta property="og:type" content="${escapeAttr(data.ogType ?? "website")}" />`);
  if (data.title) {
    out.push(`<meta property="og:title" content="${escapeAttr(data.title)}" />`);
  }
  if (data.description) {
    out.push(`<meta property="og:description" content="${escapeAttr(data.description)}" />`);
  }
  if (data.canonical) {
    out.push(`<meta property="og:url" content="${escapeAttr(data.canonical)}" />`);
  }
  if (data.ogImage) {
    out.push(`<meta property="og:image" content="${escapeAttr(data.ogImage)}" />`);
    out.push(`<meta name="twitter:card" content="summary_large_image" />`);
  }
  for (const doc of data.jsonLd ?? []) {
    out.push(`<script type="application/ld+json">${escapeJsonLd(doc)}</script>`);
  }
  return out.join("\n    ");
}

/**
 * Build a page's canonical URL plus one alternate per supported language.
 *
 * Language travels in a `?lang=` param rather than a path prefix: the cabinet's
 * 40 existing routes are not locale-prefixed, and adding a prefix would move
 * every one of them.
 */
export function buildCanonical(
  origin: string,
  pathname: string,
  langs: readonly string[],
  currentLang: string,
): { canonical: string; alternates: Record<string, string> } {
  const clean = pathname.replace(/\/+$/, "") || "/";
  const base = `${origin}${clean}`;
  const alternates: Record<string, string> = {};
  for (const lang of langs) {
    alternates[lang] = lang === "ru" ? base : `${base}?lang=${lang}`;
  }
  alternates["x-default"] = base;
  return {
    canonical: currentLang === "ru" ? base : `${base}?lang=${currentLang}`,
    alternates,
  };
}
