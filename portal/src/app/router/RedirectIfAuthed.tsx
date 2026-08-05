import { Navigate, Outlet, useLocation } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { isSafeReturnPath } from "@/shared/config";

/**
 * Keeps already-authenticated users out of the login/OTP screens.
 *
 * It honours `state.from` for the same reason `OtpPage` does, and it is not
 * optional that both do: this guard re-renders the instant the verify writes a
 * token, so an unconditional `/cabinet` here overruled whatever the OTP screen
 * had computed and every deep link still landed on the cabinet home — the fix
 * to `OtpPage` alone changed nothing observable.
 */
export function RedirectIfAuthed() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const from = (useLocation().state as { from?: string } | null)?.from;
  if (isAuthenticated) {
    return <Navigate to={from && isSafeReturnPath(from) ? from : "/cabinet"} replace />;
  }
  return <Outlet />;
}
