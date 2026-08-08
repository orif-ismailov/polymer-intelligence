/**
 * The marketplace's public URL contract.
 *
 * These paths are crawled and linked from outside, so they are the one part of
 * the route table that cannot be renamed without a redirect. `DIRECTORY_SLUGS`
 * mirrors the same map in `backend/app/api/public.py` — the slug is what the API
 * takes as `/public/directories/{slug}`, so the two drifting means a live
 * directory 404s.
 */

/** A company directory that has a public page. */
export interface PublicDirectory {
  /** URL segment AND the API's `slug` path param. */
  slug: string;
  /** The confirmed business role a company needs to be listed. */
  role: string;
  /** i18n key for the nav label and page title. */
  labelKey: string;
  /** i18n key for the page subtitle. */
  subtitleKey: string;
}

export const PUBLIC_DIRECTORIES: readonly PublicDirectory[] = [
  {
    slug: "manufacturers",
    role: "manufacturer",
    labelKey: "nav.manufacturers",
    subtitleKey: "public.directories.manufacturers.subtitle",
  },
  {
    slug: "traders",
    role: "trader",
    labelKey: "public.nav.traders",
    subtitleKey: "public.directories.traders.subtitle",
  },
  {
    slug: "logistics",
    role: "logistics_provider",
    labelKey: "public.nav.logistics",
    subtitleKey: "public.directories.logistics.subtitle",
  },
  {
    slug: "laboratories",
    role: "laboratory",
    labelKey: "public.nav.laboratories",
    subtitleKey: "public.directories.laboratories.subtitle",
  },
] as const;

export function directoryBySlug(slug: string | undefined): PublicDirectory | null {
  if (!slug) return null;
  return PUBLIC_DIRECTORIES.find((d) => d.slug === slug) ?? null;
}

/**
 * The directory a company's confirmed roles put it in, in `PUBLIC_DIRECTORIES`
 * order — the same precedence the company page uses for its canonical URL.
 *
 * The API's profile endpoint is scoped to the directory in the path, so a link
 * built with the wrong slug 404s: a trader's offer used to link its seller to
 * `/manufacturers/:id`, which resolves for a manufacturer and for nobody else.
 * Returns `null` when no confirmed role has a public directory (an importer /
 * distributor-only company has no profile page to link to).
 */
export function directoryForRoles(
  roles: readonly string[] | null | undefined,
): PublicDirectory | null {
  if (!roles || roles.length === 0) return null;
  return PUBLIC_DIRECTORIES.find((d) => roles.includes(d.role)) ?? null;
}

/**
 * URL prefix every authenticated page lives under.
 *
 * One string, because three different things have to agree on it: the route
 * tree, the tier a shared page is currently rendering in (`useTierBase`), and
 * the 401 handler that decides whether a failed refresh is a dead end or the
 * normal state of a visitor who happens to be reading the storefront.
 * `server.js` re-declares it as a literal for the same reason it re-declares
 * the public patterns — it boots before the bundle.
 */
export const CABINET_BASE = "/cabinet";

/** Is this pathname inside the cabinet (i.e. does it require a session)? */
export function isCabinetPath(pathname: string): boolean {
  return pathname === CABINET_BASE || pathname.startsWith(`${CABINET_BASE}/`);
}

/**
 * May we send a freshly-signed-in visitor to this `state.from`?
 *
 * The test is "same-origin relative path", NOT "inside the cabinet". Two places
 * decide where the login flow lands — `OtpPage` after a successful verify, and
 * `RedirectIfAuthed` the moment the token appears — and they have to agree, or
 * whichever renders second silently overrules the other. That is the shape the
 * bug actually had: `OtpPage` tested `isCabinetPath`, so every storefront return
 * path was dropped; and even once it accepted them, the guard still redirected
 * to `/cabinet` regardless. One predicate, imported by both.
 *
 * `//evil.com` is a protocol-relative URL the browser resolves as another
 * origin, so a leading `//` is rejected — this value arrives from router state a
 * link supplied, and an open redirect is the one thing it must not become.
 */
export function isSafeReturnPath(path: string): boolean {
  return path.startsWith("/") && !path.startsWith("//");
}

/**
 * Paths that are server-rendered.
 *
 * These are the marketplace's crawlable URLs and the one part of the route table
 * that cannot be renamed without a redirect. The server has no session — the
 * refresh cookie is scoped to `/api/v1/portal` and the access token lives in
 * memory — so it renders the anonymous view of these paths for everyone,
 * including signed-in visitors, whose chrome resolves after the boot-time
 * refresh. That is what keeps the HTML shared-cacheable.
 */
export const SERVER_RENDERED_PATTERNS: readonly RegExp[] = [
  /^\/$/,
  /^\/market\/?$/,
  /^\/market\/\d+\/?$/,
  /^\/prices\/?$/,
  /^\/news\/?$/,
  /^\/news\/\d+\/?$/,
  ...PUBLIC_DIRECTORIES.map((d) => new RegExp(`^/${d.slug}/?$`)),
  ...PUBLIC_DIRECTORIES.map((d) => new RegExp(`^/${d.slug}/\\d+/?$`)),
] as const;

/** Does this pathname get server-rendered content, or just the app shell? */
export function isServerRenderedPath(pathname: string): boolean {
  return SERVER_RENDERED_PATTERNS.some((re) => re.test(pathname));
}
