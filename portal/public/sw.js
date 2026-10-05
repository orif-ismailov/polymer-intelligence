/*
 * IMEX AI service worker — what makes the portal an installable PWA.
 *
 * Deliberately small, and deliberately NOT an offline copy of the site:
 *
 * - `/api/*` is never touched. Every answer there depends on who is asking, and
 *   a cached one would show one visitor's cabinet to another, or a stale price.
 * - Page HTML is never cached either. Public pages are server-rendered and
 *   shared-cached by the server for 60 s already; the cabinet is a session
 *   shell. A navigation goes to the network, and only when the network is GONE
 *   does it get `/offline.html` instead of the browser's dinosaur.
 * - `/assets/*` are Vite's content-hashed bundles — a changed file is a new
 *   URL, so cache-first is exactly right and can never serve stale code.
 *
 * Bump VERSION to drop every cache this worker created.
 */
const VERSION = "v1";
const SHELL_CACHE = `imex-shell-${VERSION}`;
const ASSET_CACHE = `imex-assets-${VERSION}`;
const SHELL = ["/offline.html", "/icon-192.png", "/favicon.ico"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("imex-") && key !== SHELL_CACHE && key !== ASSET_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match("/offline.html").then((page) => page ?? Response.error()),
      ),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.open(ASSET_CACHE).then((cache) =>
        cache.match(request).then(
          (hit) =>
            hit ??
            fetch(request).then((response) => {
              if (response.ok) cache.put(request, response.clone());
              return response;
            }),
        ),
      ),
    );
  }
});
