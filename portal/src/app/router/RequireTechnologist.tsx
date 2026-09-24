import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "@/entities/account";

/**
 * The expert cabinet (`/cabinet/expert/*`) is for accounts that applied as a
 * technologist. A company account landing here — an old link, a typed URL —
 * goes to its own home; the API would answer 403 `not_a_technologist` anyway.
 */
export function RequireTechnologist() {
  const isExpert = useAuthStore((s) => s.account?.applied_as === "technologist");
  return isExpert ? <Outlet /> : <Navigate to="/cabinet" replace />;
}
