import { StrictMode } from "react";

import type { DehydratedState } from "@tanstack/react-query";
import { hydrateRoot } from "react-dom/client";
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
 * `hydrateRoot`, not `createRoot`: the server already sent markup for this URL
 * and re-rendering from scratch would throw it away, flash the page, and cost
 * the LCP the SSR was added to win.
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

hydrateRoot(
  container,
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
  </StrictMode>,
);
