import { create } from "zustand";

import { RAIL_COLLAPSED_KEY } from "@/shared/config";

/**
 * Whether the cabinet's side rail is collapsed to its icon width.
 *
 * A UI preference, not a credential, so it persists to localStorage the way the
 * theme and the active company do. Lives in `shared/` because the widget that
 * draws the rail and the shell that reserves its width both need it, and the
 * two sit in different FSD layers.
 *
 * `readInitial` is wrapped because `shared/lib` is imported during the SSR of
 * every public page, where `localStorage` does not exist — the same reason
 * `theme.ts` and `activeCompanyStore.ts` wrap theirs. Reading it at store
 * construction (rather than in an effect) is what keeps the rail from painting
 * expanded and then snapping shut on the first client frame.
 */

/** Expanded and collapsed rail widths, as the CSS the shell interpolates. */
export const RAIL_WIDTH = "15.5rem";
export const RAIL_WIDTH_COLLAPSED = "4rem";

function readInitial(): boolean {
  try {
    return localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

interface RailState {
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggle: () => void;
}

export const useRailStore = create<RailState>((set, get) => ({
  collapsed: readInitial(),
  setCollapsed: (collapsed) => {
    try {
      localStorage.setItem(RAIL_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      // Persistence is best-effort — the in-memory choice still applies.
    }
    set({ collapsed });
  },
  toggle: () => {
    get().setCollapsed(!get().collapsed);
  },
}));
