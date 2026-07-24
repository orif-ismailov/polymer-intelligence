import { type ReactNode, useEffect } from "react";

import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";

/**
 * Applies the initial theme + keeps <html lang> in sync with i18n. The portal
 * ships a single light theme for now; the `data-theme` hook stays so a dark
 * mode can be added by flipping the attribute without touching components.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", "light");
    root.lang = coerceLang(i18n.language);
  }, [i18n.language]);

  return <>{children}</>;
}
