/**
 * Auth bridge — decouples the business-agnostic fetch client (this `shared`
 * layer) from the account entity's zustand store, which lives in `entities`.
 *
 * FSD forbids `shared` importing from `entities`. Instead the account store
 * *registers* accessors here at app boot; the client reads them through this
 * indirection. If nothing is registered (e.g. in a unit test), calls degrade to
 * an anonymous request with no retry.
 */

export interface AuthBridge {
  /** Current in-memory access token, or null when anonymous. */
  getToken: () => string | null;
  /** Persist a freshly refreshed token. */
  setToken: (token: string) => void;
  /** Wipe auth state (called after an unrecoverable 401). */
  clear: () => void;
}

let bridge: AuthBridge | null = null;

export function registerAuthBridge(next: AuthBridge): void {
  bridge = next;
}

export function getAuthToken(): string | null {
  return bridge?.getToken() ?? null;
}

export function setAuthToken(token: string): void {
  bridge?.setToken(token);
}

export function clearAuth(): void {
  bridge?.clear();
}
