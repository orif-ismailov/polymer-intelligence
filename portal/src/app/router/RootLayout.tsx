import { Outlet, ScrollRestoration } from "react-router-dom";

/**
 * The one route every other route hangs under, and the only thing it renders
 * besides its children is scroll behaviour.
 *
 * Without it a client-side navigation left the window exactly where it was:
 * opening a listing from halfway down `/market` dropped you halfway down the
 * product sheet, and a nav click from the bottom of the storefront landed
 * mid-page on `/news`. A browser resets scroll on a real document load, so this
 * only ever went wrong on the transitions the SPA handles itself — which is
 * most of them.
 *
 * `<ScrollRestoration>` is the router's own answer and it is more careful than
 * a `window.scrollTo(0, 0)` in an effect would be. Per navigation type:
 *
 * - **push** (a link) → top, which is the bug above.
 * - **pop** (back/forward) → the offset that entry was left at, read from
 *   `sessionStorage`. Scrolling someone back to the top of a list they had
 *   worked their way down is the other half of getting this wrong.
 * - **`#hash`** → the element, not the top. `PublicOfferPage`'s in-page jumps
 *   are plain `scrollIntoView` calls from click handlers rather than
 *   navigations, so they never reach this — but a real anchor link would.
 * - **`<Link preventScrollReset>`** → nothing, for the tab-strip and filter
 *   links that write to the URL without changing the page under it.
 *
 * It has to live INSIDE the router (it reads the navigation), which is why it
 * is a layout route rather than something wrapped around `<RouterProvider>` in
 * `entry-client`. It renders `null` here — the `<script>` it can emit belongs to
 * framework mode, and this app builds its own routers from the `routes` array —
 * so it costs the SSR markup nothing and cannot desync hydration.
 */
export function RootLayout() {
  return (
    <>
      <ScrollRestoration />
      <Outlet />
    </>
  );
}
