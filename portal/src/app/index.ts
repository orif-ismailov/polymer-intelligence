/**
 * The app layer no longer exports a single `<App/>`.
 *
 * There are two entries now, and they compose the providers differently:
 * `entry-client.tsx` adds `AppBootstrap` (the session refresh) and
 * `ThemeProvider` (a DOM effect); `entry-server.tsx` deliberately omits both,
 * because the server has no cookie to refresh with and no document to theme.
 * A shared `<App/>` would have had to branch on the environment internally,
 * which is the thing that makes SSR bugs hard to see.
 */
export { AppBootstrap } from "./AppBootstrap";
export { routes } from "./router/routes";
