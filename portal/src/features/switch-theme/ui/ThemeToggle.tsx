import { useEffect, useState } from "react";

import { Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { resolveTheme, useThemeStore } from "@/shared/lib";
import { IconButton } from "@/shared/ui";

interface ThemeToggleProps {
  className?: string;
}

/**
 * One click between the dark and the light theme, from any header.
 *
 * The preference is the same store Settings writes (`shared/lib/theme`), so the
 * two never disagree; «Системная» stays a Settings choice — a header button that
 * cycled through three states would be a puzzle, not a switch.
 *
 * The storefront is SERVER-rendered and the server cannot know the stored
 * theme, so until the client has mounted the icon is the default theme's. Any
 * other value would differ from the server HTML and fail hydration.
 */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { t } = useTranslation();
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const current = mounted ? resolveTheme(mode) : "dark";
  const next = current === "dark" ? "light" : "dark";

  return (
    <IconButton
      label={t(`theme.switchTo.${next}`)}
      onClick={() => setMode(next)}
      className={className}
      data-testid="theme-toggle"
    >
      {current === "dark" ? (
        <Sun size={18} strokeWidth={1.75} aria-hidden />
      ) : (
        <Moon size={18} strokeWidth={1.75} aria-hidden />
      )}
    </IconButton>
  );
}
