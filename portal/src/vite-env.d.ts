/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  /**
   * TanStack Query cache the SSR render dehydrated, inlined into the HTML by
   * server.js. `entry-client` passes it to `HydrationBoundary` so the browser
   * reuses the server's fetches instead of repeating them.
   */
  __QUERY_STATE__?: unknown;
  /**
   * Public origin the storefront is served from, injected per request so
   * canonical URLs survive a domain change without a rebuild.
   */
  __PUBLIC_SITE_ORIGIN__?: string;
  /**
   * The language the server rendered this HTML in. i18n initializes with it so
   * the client's first render matches the markup; the user's own preference is
   * applied after hydration.
   */
  __SSR_LANG__?: string;
}
