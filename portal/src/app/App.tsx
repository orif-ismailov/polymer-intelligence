import { RouterProvider } from "react-router-dom";

import "@/shared/i18n";
import "@/entities/account";

import { AppBootstrap } from "./AppBootstrap";
import { QueryProvider } from "./providers/QueryProvider";
import { ThemeProvider } from "./providers/ThemeProvider";
import { router } from "./router/routes";

/**
 * Application root. Provider order matters:
 *  QueryProvider → ThemeProvider → AppBootstrap → RouterProvider.
 * The two side-effect imports above guarantee i18n initializes and the auth
 * store registers its bridge with the fetch client before anything renders.
 */
export function App() {
  return (
    <QueryProvider>
      <ThemeProvider>
        <AppBootstrap>
          <RouterProvider router={router} />
        </AppBootstrap>
      </ThemeProvider>
    </QueryProvider>
  );
}
