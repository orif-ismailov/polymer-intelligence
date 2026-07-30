import { create } from "zustand";

/**
 * Ephemeral state shared between the phone screen and the code screen: which
 * phone the OTP was sent to and the initial resend cooldown. Not persisted —
 * refreshing on /login/code without a pending phone bounces back to /login.
 */
interface AuthFlowState {
  phone: string | null;
  cooldownSeconds: number;
  setPending: (phone: string, cooldownSeconds: number) => void;
  clear: () => void;
}

export const useAuthFlowStore = create<AuthFlowState>((set) => ({
  phone: null,
  cooldownSeconds: 0,
  setPending: (phone, cooldownSeconds) => set({ phone, cooldownSeconds }),
  clear: () => set({ phone: null, cooldownSeconds: 0 }),
}));
