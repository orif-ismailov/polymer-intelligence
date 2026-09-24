import { useEffect, type ReactNode } from "react";

import { useBootstrapAuth } from "@/entities/account";
import { StepUpDialog } from "@/features/step-up";
import { coerceLang, i18n, preferredLanguage, setLanguage, SUPPORTED_LANGS } from "@/shared/i18n";

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
    // A link that names its language (`?lang=fa` — the hreflang alternates, a
    // shared URL) is an explicit choice: keep it, and remember it, rather than
    // flipping the page to the browser's language right after it rendered.
    const asked = new URLSearchParams(window.location.search).get("lang");
    if (asked && (SUPPORTED_LANGS as readonly string[]).includes(asked)) {
      setLanguage(coerceLang(asked));
      return;
    }
    const preferred = preferredLanguage();
    if (preferred !== i18n.language) {
      void i18n.changeLanguage(preferred);
    }
  }, []);

  // Mounted once, above the router: the 403 that opens it can come from a mutation
  // fired on any screen, and it must survive the navigation that mutation triggers.
  return (
    <>
      {children}
      <StepUpDialog />
    </>
  );
}
