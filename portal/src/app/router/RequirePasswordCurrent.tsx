import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "@/entities/account";

/**
 * Keeps an account that owes a first-login password change off every other screen.
 *
 * The API is the real boundary — `get_current_account` answers 403
 * `password_change_required` — so this guard is not what enforces the rule. What it
 * does is make the refusal legible: without it the visitor lands on the cabinet and
 * watches every panel fail with an error that explains nothing.
 *
 * **It sits ABOVE `RequireCompany`, and that order is load-bearing.** A freshly
 * issued account has no company, so below it the visitor would be bounced to
 * `/cabinet/onboarding`, whose first query 403s for this very reason — a dead end on
 * a screen that cannot say why. `/cabinet/password` is mounted as a sibling, outside
 * this guard, because it is the one route that must stay reachable.
 */
export function RequirePasswordCurrent() {
  const mustChange = useAuthStore((s) => s.account?.must_change_password ?? false);

  if (mustChange) {
    return <Navigate to="/cabinet/password" replace />;
  }
  return <Outlet />;
}
