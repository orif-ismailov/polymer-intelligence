/**
 * Role preference store (zustand).
 *
 * The first-run role hint (Buyer/Seller) sets `role`, which decides the default
 * landing tab. It is NOT a hard gate — every tab stays reachable regardless.
 * `role === null` means the hint has not been answered yet. Persisted to
 * localStorage (Phase 1+: also the client profile).
 */

import { create } from "zustand";

export type Role = "buyer" | "seller";

const STORAGE_KEY = "pi_role_pref";

function loadRole(): Role | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "buyer" || v === "seller") return v;
  } catch {
    /* ignore */
  }
  return null;
}

interface RoleStore {
  role: Role | null;
  setRole(role: Role): void;
}

export const useRoleStore = create<RoleStore>((set) => ({
  role: loadRole(),
  setRole: (role) => {
    try {
      localStorage.setItem(STORAGE_KEY, role);
    } catch {
      /* ignore */
    }
    set({ role });
  },
}));
