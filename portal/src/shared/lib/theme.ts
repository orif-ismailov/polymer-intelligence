import { create } from "zustand";

import { THEME_KEY } from "@/shared/config";

/**
 * Colour-theme preference. `dark` is the product default (the design system is a
 * dark one — see docs/design-system.md); `light` is the secondary theme and
 * `system` follows the OS.
 *
 * Lives in `shared/` because both the app-layer provider that applies the theme
 * and the Settings screen that changes it need it, and FSD forbids `pages → app`.
 */
export const THEME_MODES = ["dark", "light", "system"] as const;
export type ThemeMode = (typeof THEME_MODES)[number];

/** The two values `data-theme` can actually take. */
export type ResolvedTheme = "dark" | "light";

export const DEFAULT_THEME_MODE: ThemeMode = "dark";

function isThemeMode(value: string | null): value is ThemeMode {
  return value !== null && (THEME_MODES as readonly string[]).includes(value);
}

function readInitial(): ThemeMode {
  try {
    const raw = localStorage.getItem(THEME_KEY);
    return isThemeMode(raw) ? raw : DEFAULT_THEME_MODE;
  } catch {
    return DEFAULT_THEME_MODE;
  }
}

/** Does the OS ask for a dark UI? Falls back to dark when unknowable. */
export function prefersDark(): boolean {
  try {
    return !window.matchMedia("(prefers-color-scheme: light)").matches;
  } catch {
    return true;
  }
}

/** Collapse a preference into the concrete theme to paint. */
export function resolveTheme(mode: ThemeMode): ResolvedTheme {
  if (mode === "system") return prefersDark() ? "dark" : "light";
  return mode;
}

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: readInitial(),
  setMode: (mode) => {
    try {
      localStorage.setItem(THEME_KEY, mode);
    } catch {
      // Persistence is best-effort — the in-memory choice still applies.
    }
    set({ mode });
  },
}));
