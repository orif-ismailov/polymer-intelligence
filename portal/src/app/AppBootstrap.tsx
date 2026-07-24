import { type ReactNode } from "react";

import { useBootstrapAuth } from "@/entities/account";

/**
 * Runs the boot-time session restore inside the QueryClient/i18n providers,
 * before the router renders. The guard reads `initializing` to hold routing
 * until the refresh attempt resolves.
 */
export function AppBootstrap({ children }: { children: ReactNode }) {
  useBootstrapAuth();
  return <>{children}</>;
}
