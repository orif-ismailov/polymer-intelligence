import { create } from "zustand";

import { ACTIVE_COMPANY_KEY } from "@/shared/config";

/**
 * The currently-selected company scopes the offers view and dashboard cards.
 * Persisted to localStorage (a UI preference, not a credential) so the choice
 * survives reloads.
 */
interface ActiveCompanyState {
  activeCompanyId: number | null;
  setActiveCompany: (id: number | null) => void;
}

function readInitial(): number | null {
  try {
    const raw = localStorage.getItem(ACTIVE_COMPANY_KEY);
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export const useActiveCompanyStore = create<ActiveCompanyState>((set) => ({
  activeCompanyId: readInitial(),
  setActiveCompany: (id) => {
    try {
      if (id == null) {
        localStorage.removeItem(ACTIVE_COMPANY_KEY);
      } else {
        localStorage.setItem(ACTIVE_COMPANY_KEY, String(id));
      }
    } catch {
      // Persistence is best-effort.
    }
    set({ activeCompanyId: id });
  },
}));
