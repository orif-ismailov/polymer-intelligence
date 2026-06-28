/**
 * ThemeProvider — applies the resolved color scheme to <html data-theme>.
 *
 * Resolution order (docs/design-system.md §2):
 *   1. Manual override (themeStore.pref, surfaced in Профиль) when not 'system'.
 *   2. Otherwise follow the platform scheme — Telegram WebApp.colorScheme in the
 *      Mini App, prefers-color-scheme in a browser — and live-update on change.
 */

import { useEffect, type ReactNode } from "react";

import { getColorScheme, onColorSchemeChange } from "../telegram";
import { resolveScheme, useThemeStore } from "./themeStore";

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const pref = useThemeStore((s) => s.pref);
  const systemScheme = useThemeStore((s) => s.systemScheme);
  const setSystemScheme = useThemeStore((s) => s.setSystemScheme);

  // Seed + subscribe to the platform color scheme.
  useEffect(() => {
    setSystemScheme(getColorScheme());
    return onColorSchemeChange(setSystemScheme);
  }, [setSystemScheme]);

  // Apply the resolved scheme to the document root.
  useEffect(() => {
    document.documentElement.dataset.theme = resolveScheme(pref, systemScheme);
  }, [pref, systemScheme]);

  return <>{children}</>;
}
