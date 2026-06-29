/**
 * Theme preference store (zustand).
 *
 * `pref` is the user's choice persisted in localStorage and (Phase 1+) on the
 * client profile: 'dark' (default — the brand look), 'system' (follow Telegram's
 * colorScheme), or 'light'. `systemScheme` is the live platform scheme kept up to date by
 * ThemeProvider. The resolved scheme = pref === 'system' ? systemScheme : pref.
 */

import { create } from "zustand";

export type ThemePref = "system" | "light" | "dark";
export type ColorScheme = "light" | "dark";

const STORAGE_KEY = "pi_theme_pref";

function loadPref(): ThemePref {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "system" || v === "light" || v === "dark") return v;
  } catch {
    /* ignore — private mode / no storage */
  }
  // Default to dark (the brand look) until the user explicitly picks System/Light
  // in Профиль. design-system.md §2 dark-first.
  return "dark";
}

interface ThemeStore {
  pref: ThemePref;
  systemScheme: ColorScheme;
  setPref(pref: ThemePref): void;
  setSystemScheme(scheme: ColorScheme): void;
}

export const useThemeStore = create<ThemeStore>((set) => ({
  pref: loadPref(),
  systemScheme: "dark",
  setPref: (pref) => {
    try {
      localStorage.setItem(STORAGE_KEY, pref);
    } catch {
      /* ignore */
    }
    set({ pref });
  },
  setSystemScheme: (systemScheme) => set({ systemScheme }),
}));

/** Resolve the effective scheme from the preference + live platform scheme. */
export function resolveScheme(pref: ThemePref, systemScheme: ColorScheme): ColorScheme {
  return pref === "system" ? systemScheme : pref;
}

/** Convenience hook: { pref, scheme, setPref }. */
export function useTheme(): {
  pref: ThemePref;
  scheme: ColorScheme;
  setPref: (pref: ThemePref) => void;
} {
  const pref = useThemeStore((s) => s.pref);
  const systemScheme = useThemeStore((s) => s.systemScheme);
  const setPref = useThemeStore((s) => s.setPref);
  return { pref, scheme: resolveScheme(pref, systemScheme), setPref };
}
