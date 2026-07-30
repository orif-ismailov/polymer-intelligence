import { type ReactNode, useEffect } from "react";

import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";
import { resolveTheme, useThemeStore } from "@/shared/lib";

/**
 * Applies the colour theme to <html data-theme> and keeps <html lang> in sync
 * with i18n. The preference itself lives in `shared/lib/theme` (the Settings
 * screen writes it); this provider is only the DOM effect.
 *
 * First paint is handled by the inline bootstrap script in `index.html`, so this
 * effect normally re-applies the same value — it exists to react to later
 * changes (the switcher, and OS changes while `mode === "system"`).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const mode = useThemeStore((s) => s.mode);

  useEffect(() => {
    const root = document.documentElement;
    const apply = (): void => {
      root.setAttribute("data-theme", resolveTheme(mode));
    };
    apply();

    if (mode !== "system") return;

    // Follow the OS for as long as the preference is "system".
    const query = window.matchMedia("(prefers-color-scheme: light)");
    query.addEventListener("change", apply);
    return () => {
      query.removeEventListener("change", apply);
    };
  }, [mode]);

  useEffect(() => {
    document.documentElement.lang = coerceLang(i18n.language);
  }, [i18n.language]);

  return <>{children}</>;
}
