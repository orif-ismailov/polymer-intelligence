/**
 * Portal SSR server.
 *
 * Public routes are rendered to HTML here; everything behind the login is sent
 * as the app shell and rendered in the browser. That split is deliberate: the
 * access token lives in memory and the refresh cookie is httpOnly and scoped to
 * `/api/v1/portal`, so this process has no session to render a cabinet page
 * from and must not acquire one.
 *
 * Runs in two modes from one file:
 *  - dev  (`npm run dev`)  — Vite middleware, HMR, module graph reloaded per request
 *  - prod (`npm start`)    — prebuilt client assets + the compiled server bundle
 *
 * Plain JavaScript rather than TypeScript so production `node server.js` needs
 * no build step or loader of its own.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const isProd = process.env.NODE_ENV === "production";
const port = Number(process.env.PORT || 3000);

/**
 * Where this process reaches the API. Internal address under compose
 * (`http://api:8000`), so a render never leaves the network and comes back in
 * through nginx.
 */
const INTERNAL_API_ORIGIN = process.env.INTERNAL_API_ORIGIN || "http://127.0.0.1:8000";

/**
 * Public origin the storefront is served from. Drives canonical URLs, og:url,
 * sitemap.xml and robots.txt. Moving the marketplace to another domain is this
 * one variable and an nginx vhost; nothing is baked into the bundle.
 */
const PUBLIC_SITE_ORIGIN = (process.env.PUBLIC_SITE_ORIGIN || "").replace(/\/+$/, "");

/** Supported UI languages. Mirrors SUPPORTED_LANGS in shared/i18n. */
const LANGS = ["ru", "uz", "en"];

globalThis.__INTERNAL_API_ORIGIN__ = INTERNAL_API_ORIGIN;

/**
 * Paths that get server-rendered content. Everything else is the shell.
 * Mirrors SERVER_RENDERED_PATTERNS in shared/config/publicRoutes.ts — kept as a
 * literal here because this file runs before the bundle is loaded in prod.
 */
const DIRECTORY_SLUGS = ["manufacturers", "traders", "logistics", "laboratories"];
const PUBLIC_PATTERNS = [
  /^\/$/,
  /^\/market\/?$/,
  /^\/market\/\d+\/?$/,
  /^\/prices\/?$/,
  /^\/news\/?$/,
  /^\/news\/\d+\/?$/,
  ...DIRECTORY_SLUGS.map((s) => new RegExp(`^/${s}/?$`)),
  ...DIRECTORY_SLUGS.map((s) => new RegExp(`^/${s}/\\d+/?$`)),
];

function isPublicPath(pathname) {
  return PUBLIC_PATTERNS.some((re) => re.test(pathname));
}

/**
 * Cabinet URLs from before the `/cabinet` prefix existed.
 *
 * R1–R3 shipped with the cabinet at the root, so these are in bookmarks, in
 * browser history, and in links already sent to customers. They redirect for
 * real, in Express, rather than as a react-router `<Navigate>`, for two reasons:
 * a 301 is what a crawler and a `curl` follow, and the SSR path cannot emit one
 * anyway — `entry-server.tsx` returns only a status and drops the router's
 * `Location` header (see the render handler below).
 *
 * `/market/favorites` and `/market/requests` are listed explicitly because
 * `/market` itself stays public; only those two leaves moved.
 */
const LEGACY_CABINET_PATHS = [
  "/login",
  "/onboarding",
  "/companies",
  "/offers",
  "/deals",
  "/contracts",
  "/inquiries",
  "/requests",
  "/samples",
  "/lab-orders",
  "/settings",
  "/notifications",
  "/sellers",
  "/market/favorites",
  "/market/requests",
];

/**
 * Resolve the render language: `?lang=`, then the preference cookie, then
 * Accept-Language, then ru.
 *
 * The cookie is what `setLanguage` writes in the browser. Without it the server
 * could only guess from Accept-Language, and a visitor who had explicitly chosen
 * a language would get every page rendered in another one and corrected after
 * hydration.
 */
function resolveLang(req) {
  const queryLang = req.query?.lang;
  if (typeof queryLang === "string" && LANGS.includes(queryLang)) return queryLang;

  const cookie = req.headers.cookie;
  if (typeof cookie === "string") {
    const match = /(?:^|;\s*)portal\.language=([^;]+)/.exec(cookie);
    if (match && LANGS.includes(match[1])) return match[1];
  }

  const header = req.headers["accept-language"];
  if (typeof header === "string") {
    for (const part of header.split(",")) {
      const code = part.trim().slice(0, 2).toLowerCase();
      if (LANGS.includes(code)) return code;
    }
  }
  return "ru";
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Serialize state for a `<script>` tag. `<` must be escaped or a string
 * containing `</script>` ends the block early and the rest of the JSON becomes
 * markup — the classic XSS in an SSR state payload.
 */
function serializeState(value) {
  return JSON.stringify(value ?? null)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

/**
 * Everything between the two ssr-head markers, inclusive. The template carries
 * fallback tags inside them, so this replaces the block rather than filling a
 * gap — otherwise the fallback `<title>` ships alongside the rendered one.
 */
const HEAD_BLOCK = /<!--ssr-head-->[\s\S]*?<!--\/ssr-head-->/;

function applyTemplate(template, { head, body, state }) {
  return template
    .replace(HEAD_BLOCK, head)
    .replace("<!--ssr-outlet-->", body)
    .replace("<!--ssr-state-->", state);
}

/**
 * Dev-only: make the stylesheet render-blocking, the way the production build
 * already is.
 *
 * `vite build` extracts the CSS and writes a `<link rel="stylesheet">` into
 * dist/client/index.html, so prod paints styled. Dev has no such link — the CSS
 * arrives through `import "@/app/styles.css"` in entry-client and is injected by
 * JS once the module graph loads. Against SSR that means the server's HTML paints
 * unstyled first and restyles a moment later, which reads as a flash on every
 * reload. `?direct` is what makes Vite serve the compiled sheet as text/css
 * rather than the JS module that injects it. HMR is unaffected: the injected
 * <style> lands after this link and wins.
 */
function withDevStylesheet(template) {
  const link = '<link rel="stylesheet" href="/src/app/styles.css?direct" />';
  return template.includes(link) ? template : template.replace("</head>", `  ${link}\n  </head>`);
}

function siteOrigin(req) {
  if (PUBLIC_SITE_ORIGIN) return PUBLIC_SITE_ORIGIN;
  // Behind nginx the socket is plain HTTP, so trust the forwarded proto.
  const proto = req.headers["x-forwarded-proto"] || req.protocol || "https";
  return `${proto}://${req.headers.host}`;
}

async function createServer() {
  const app = express();
  app.disable("x-powered-by");

  let vite;
  let templateHtml = "";
  let ssrRender;

  if (isProd) {
    const compression = (await import("compression")).default;
    const sirv = (await import("sirv")).default;
    app.use(compression());
    // Hashed asset filenames are immutable; index.html never is.
    app.use(
      sirv(path.resolve(rootDir, "dist/client"), { extensions: [], maxAge: 31536000, immutable: true }),
    );
    templateHtml = await fs.readFile(path.resolve(rootDir, "dist/client/index.html"), "utf-8");
    ssrRender = (await import("./dist/server/entry-server.js")).render;
  } else {
    const { createServer: createViteServer } = await import("vite");
    vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "custom",
    });
    app.use(vite.middlewares);
  }

  // ── Optional same-origin /api proxy (local preview only) ──────────────────
  //
  // In every real deployment nginx serves the API same-origin at /api/ and this
  // process never sees those requests. Standalone `npm start` has no nginx, so
  // /api/* would fall through to the page renderer and the browser would parse
  // HTML as JSON. Opt-in, so production behaviour is unchanged and a missing
  // nginx route still fails loudly instead of being silently papered over here.
  if (process.env.DEV_API_PROXY === "1") {
    app.use("/api", async (req, res) => {
      const target = `${INTERNAL_API_ORIGIN}/api${req.url}`;
      try {
        const upstream = await fetch(target, {
          method: req.method,
          headers: { ...req.headers, host: new URL(INTERNAL_API_ORIGIN).host },
          body: ["GET", "HEAD"].includes(req.method) ? undefined : req,
          duplex: "half",
          redirect: "manual",
        });
        res.status(upstream.status);
        upstream.headers.forEach((v, k) => {
          if (k !== "content-encoding" && k !== "content-length") res.setHeader(k, v);
        });
        res.send(Buffer.from(await upstream.arrayBuffer()));
      } catch (err) {
        console.error("[ssr] api proxy failed:", err.message);
        res.status(502).json({ detail: "upstream unavailable" });
      }
    });
    console.log("[portal] DEV_API_PROXY on: /api -> " + INTERNAL_API_ORIGIN);
  }

  // ── Legacy cabinet URLs ───────────────────────────────────────────────────
  //
  // Ahead of the page renderer so a bookmark never reaches it. `req.url` carries
  // the query string; only the path is rewritten.
  app.get(
    LEGACY_CABINET_PATHS.flatMap((p) => [p, `${p}/*`]),
    (req, res) => {
      const [path, query] = req.originalUrl.split("?");
      res.redirect(301, `/cabinet${path}${query ? `?${query}` : ""}`);
    },
  );

  // ── robots.txt ────────────────────────────────────────────────────────────
  //
  // One line, because every authenticated page now lives under one prefix.
  // Those pages already answer with a `noindex` meta, but a crawler should not
  // have to fetch 30 authenticated routes to discover that — and the per-route
  // list this replaces had already drifted (it never covered `/sellers` or
  // `/manufacturers/rfqs`).
  app.get("/robots.txt", (req, res) => {
    const origin = siteOrigin(req);
    res.type("text/plain").send(
      [
        "User-agent: *",
        "Allow: /",
        "Disallow: /cabinet",
        "",
        `Sitemap: ${origin}/sitemap.xml`,
        "",
      ].join("\n"),
    );
  });

  // ── sitemap.xml ───────────────────────────────────────────────────────────
  app.get("/sitemap.xml", async (req, res) => {
    const origin = siteOrigin(req);
    const staticPaths = ["/", "/market", "/prices", "/news", ...DIRECTORY_SLUGS.map((s) => `/${s}`)];

    let entries = [];
    let truncated = false;
    try {
      const resp = await fetch(`${INTERNAL_API_ORIGIN}/api/v1/public/sitemap`, {
        headers: { Accept: "application/json" },
      });
      if (resp.ok) {
        const body = await resp.json();
        entries = Array.isArray(body.entries) ? body.entries : [];
        truncated = Boolean(body.truncated);
      }
    } catch (err) {
      // Still emit the static section: a partial sitemap beats a 500.
      console.warn("[ssr] sitemap fetch failed:", err.message);
    }

    if (truncated) {
      console.warn(
        "[ssr] sitemap truncated at the 50k-URL protocol limit; a sitemap index is now needed",
      );
    }

    const urls = [
      ...staticPaths.map((p) => ({ path: p, lastmod: null })),
      ...entries,
    ];

    const xml = [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
      ...urls.map((entry) => {
        const loc = `${origin}${entry.path}`;
        const lastmod = entry.lastmod
          ? `<lastmod>${escapeHtml(String(entry.lastmod).slice(0, 10))}</lastmod>`
          : "";
        return `  <url><loc>${escapeHtml(loc)}</loc>${lastmod}</url>`;
      }),
      "</urlset>",
      "",
    ].join("\n");

    res.type("application/xml").send(xml);
  });

  // ── Page render ───────────────────────────────────────────────────────────
  app.use(async (req, res, next) => {
    if (req.method !== "GET") return next();

    const url = req.originalUrl;
    const pathname = req.path;
    const origin = siteOrigin(req);

    try {
      let template;
      let render = ssrRender;

      if (isProd) {
        template = templateHtml;
      } else {
        template = await fs.readFile(path.resolve(rootDir, "index.html"), "utf-8");
        template = await vite.transformIndexHtml(url, template);
        template = withDevStylesheet(template);
        render = (await vite.ssrLoadModule("/src/entry-server.tsx")).render;
      }

      const lang = resolveLang(req);
      // `__SSR_LANG__` must be set BEFORE the bundle runs: i18n initializes at
      // import time, and it has to start in the language this HTML was rendered
      // in or hydration fails on every translated string.
      const injected = [
        `<script>window.__PUBLIC_SITE_ORIGIN__=${serializeState(origin)};` +
          `globalThis.__PUBLIC_SITE_ORIGIN__=window.__PUBLIC_SITE_ORIGIN__;` +
          `window.__SSR_LANG__=${serializeState(lang)};` +
          `globalThis.__SSR_LANG__=window.__SSR_LANG__;</script>`,
      ];

      // Everything outside the public storefront — the whole `/cabinet` tree —
      // is shell only. Nothing to render without a session, and `noindex` so a
      // crawler that finds one does not keep it. This is a whitelist, so the
      // prefix needed no edit here: `/cabinet/**` simply never matches.
      if (!isPublicPath(pathname)) {
        const html = applyTemplate(template, {
          head: '<title>IMEX AI</title>\n    <meta name="robots" content="noindex,nofollow" />',
          body: "",
          state: injected.join(""),
        });
        return res.status(200).set({ "Content-Type": "text/html" }).send(html);
      }

      const result = await render(url, lang, origin);

      // NOTE: the target is hardcoded because `entry-server.tsx` returns only a
      // status and drops the Response — the router's `Location` never gets here.
      // Inert as written: the server has no session, so no public-tier guard
      // fires during SSR. Adding a router-level redirect without also plumbing
      // `Location` through would silently send every one of them home. Legacy
      // URL redirects are handled in Express above for exactly this reason.
      if (result.status >= 300 && result.status < 400) {
        return res.redirect(result.status, "/");
      }

      injected.push(
        `<script>window.__QUERY_STATE__=${serializeState(result.queryState)};</script>`,
      );

      const html = applyTemplate(template, {
        head: result.head,
        body: result.html,
        state: injected.join(""),
      }).replace('<html lang="ru"', `<html lang="${result.lang}"`);

      res
        .status(result.status)
        .set({
          "Content-Type": "text/html",
          // Short shared cache with a long stale window: a crawler or a burst of
          // visitors hits the edge, and one slow render never stampedes the API.
          "Cache-Control": "public, max-age=0, s-maxage=60, stale-while-revalidate=600",
        })
        .send(html);
    } catch (err) {
      if (vite) vite.ssrFixStacktrace(err);
      console.error("[ssr] render failed:", err);
      // Degrade to the client-rendered shell rather than showing an error page.
      // The bundle can still render this route in the browser; only the SEO
      // benefit is lost, and only for this request.
      try {
        const fallback = isProd
          ? templateHtml
          : await fs.readFile(path.resolve(rootDir, "index.html"), "utf-8");
        res
          .status(200)
          .set({ "Content-Type": "text/html" })
          .send(applyTemplate(fallback, { head: "", body: "", state: "" }));
      } catch {
        next(err);
      }
    }
  });

  app.listen(port, () => {
    console.log(`[portal] ${isProd ? "production" : "dev"} server on :${port}`);
    console.log(`[portal] api -> ${INTERNAL_API_ORIGIN}`);
    console.log(`[portal] public origin -> ${PUBLIC_SITE_ORIGIN || "(derived from request)"}`);
  });
}

createServer();
