import { create } from "zustand";

import { api, ApiError, registerStepUpBridge } from "@/shared/api";

/**
 * The step-up prompt, as a promise the fetch client awaits (IMEX-1).
 *
 * The client is mid-request when a sensitive action comes back 403
 * `step_up_required`; it needs a boolean before it can retry. So `open()` parks a
 * resolver in the store, the dialog renders, and whichever way the user goes —
 * confirmed, refused, cancelled — settles that one promise. A prompt that resolved
 * on render would retry before the password was typed; one that never resolved
 * would hang the mutation forever, which looks exactly like a frozen button.
 */

/**
 * An i18n key suffix, never the server's sentence. The API answers this endpoint in
 * English ("Invalid credentials") because it answers every client that way; rendering
 * that verbatim put an English line in a Russian dialog.
 */
export type StepUpError = "wrongPassword" | "unavailable" | "failed";

interface StepUpState {
  open: boolean;
  pending: boolean;
  /** Reason for the last refusal, as a key the dialog translates. */
  error: StepUpError | null;
  resolve: ((ok: boolean) => void) | null;
  prompt: () => Promise<boolean>;
  /** Resolves true when the window opened, so the caller knows whether to reset. */
  submit: (password: string) => Promise<boolean>;
  cancel: () => void;
}

function reasonFor(err: unknown): StepUpError {
  if (!(err instanceof ApiError)) return "failed";
  if (err.status === 401) return "wrongPassword";
  if (err.status === 503) return "unavailable";
  if (err.status === 429) return "failed";
  return "failed";
}

export const useStepUpStore = create<StepUpState>((set, get) => ({
  open: false,
  pending: false,
  error: null,
  resolve: null,

  prompt: () =>
    new Promise<boolean>((resolve) => {
      // A second 403 while the dialog is already up (two mutations in flight)
      // must not strand the first caller: settle it false so its request fails
      // honestly rather than waiting on a resolver this one is about to replace.
      get().resolve?.(false);
      set({ open: true, pending: false, error: null, resolve });
    }),

  submit: async (password: string) => {
    set({ pending: true, error: null });
    try {
      await api.post("/portal/auth/step-up", { password }, { skipAuthRetry: true });
    } catch (err) {
      // The dialog stays open with the typed password intact: a mistyped character
      // should cost a correction, not a full re-entry into a disabled button.
      set({ pending: false, error: reasonFor(err) });
      return false;
    }
    const { resolve } = get();
    set({ open: false, pending: false, error: null, resolve: null });
    resolve?.(true);
    return true;
  },

  cancel: () => {
    const { resolve } = get();
    set({ open: false, pending: false, error: null, resolve: null });
    resolve?.(false);
  },
}));

// Registered at module load, mirroring `authStore`'s `registerAuthBridge` — the
// bridge exists so `shared` never imports from `features`.
registerStepUpBridge({ prompt: () => useStepUpStore.getState().prompt() });
