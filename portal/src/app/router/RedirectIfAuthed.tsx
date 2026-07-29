import { Navigate, Outlet } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";

/** Keeps already-authenticated users out of the login/OTP screens. */
export function RedirectIfAuthed() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
