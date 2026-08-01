import { useEffect, type ReactNode } from "react";

import { useBootstrapAuth } from "@/entities/account";
import { i18n, preferredLanguage } from "@/shared/i18n";

/**
 * Runs the boot-time session restore inside the QueryClient/i18n providers,
 * before the router renders. The guard reads `initializing` to hold routing
 * until the refresh attempt resolves.
 */
export function AppBootstrap({ children }: { children: ReactNode }) {
  useBootstrapAuth();

  // i18n initialized with the language the SERVER rendered in, so the markup
  // matched and hydration succeeded. Now that hydration is done, move to what
  // this user actually wants. Running it in an effect is the point: doing it any
  // earlier would put it back inside the render React is trying to match.
  //
  // Usually a no-op. It only fires for a first-time visitor whose browser
  // language differs from the server's default, because `setLanguage` writes a
  // cookie the server reads on every later request.
  useEffect(() => {
    const preferred = preferredLanguage();
    if (preferred !== i18n.language) {
      void i18n.changeLanguage(preferred);
    }
  }, []);

  return <>{children}</>;
}
