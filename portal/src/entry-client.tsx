import { StrictMode } from "react";

import type { DehydratedState } from "@tanstack/react-query";
import { createRoot, hydrateRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import "@/shared/i18n";
import "@/entities/account";

import { AppBootstrap } from "@/app/AppBootstrap";
import { QueryProvider } from "@/app/providers/QueryProvider";
import { ThemeProvider } from "@/app/providers/ThemeProvider";
import { routes } from "@/app/router/routes";
import { HeadProvider } from "@/shared/seo";

import "@/app/styles.css";

/**
 * Browser entry.
 *
 * `hydrateRoot` WHERE THERE IS MARKUP TO HYDRATE: the server already rendered
 * the public storefront for this URL, and re-rendering from scratch would throw
 * it away, flash the page, and cost the LCP the SSR was added to win.
 *
 * But `server.js` answers every non-public URL — the whole `/cabinet` tree —
 * with a bare shell (`<div id="root"></div>`), deliberately: this process holds
 * no session, so there is nothing to render a cabinet page with. Hydrating an
 * empty container cannot succeed. React looks for the markup its first render
 * produced (`RequireAuth`'s spinner, while the boot-time session restore is in
 * flight), finds nothing, and reports «Expected server HTML to contain a
 * matching <div>» followed by a hydration failure — then falls back to client
 * rendering anyway. So the fallback was already the behaviour; all the failed
 * pass bought was a wasted render and a console full of errors on every cabinet
 * page load.
 *
 * The decision is read off the RESPONSE rather than from a second copy of
 * `server.js`'s public-path whitelist. Two lists would drift, and the drift
 * would show up as exactly this bug again.
 *
 * The head sink is null here. `<Seo/>` detects that and patches `document.head`
 * through an effect instead, which is the right behaviour for client-side
 * navigation, where the head the server sent belongs to a different page.
 */
const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element #root not found");
}

const router = createBrowserRouter(routes);

const app = (
  <StrictMode>
    <HeadProvider sink={null}>
      <QueryProvider
        dehydratedState={window.__QUERY_STATE__ as DehydratedState | undefined}
      >
        <ThemeProvider>
          <AppBootstrap>
            <RouterProvider router={router} />
          </AppBootstrap>
        </ThemeProvider>
      </QueryProvider>
    </HeadProvider>
  </StrictMode>
);

if (container.firstElementChild) {
  hydrateRoot(container, app);
} else {
  createRoot(container).render(app);
}
