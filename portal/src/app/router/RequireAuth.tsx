import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { selectIsAuthenticated, useAuthStore } from "@/entities/account";
import { LoadingView } from "@/shared/ui";

/**
 * Route guard for authenticated pages. While the boot-time session restore is
 * in flight it renders a spinner; once resolved, anonymous users are redirected
 * to /login (preserving the attempted path for post-login return).
 */
export function RequireAuth() {
  const { t } = useTranslation();
  const location = useLocation();
  const initializing = useAuthStore((s) => s.initializing);
  const isAuthenticated = useAuthStore(selectIsAuthenticated);

  if (initializing) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <LoadingView label={t("common.loading")} />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
