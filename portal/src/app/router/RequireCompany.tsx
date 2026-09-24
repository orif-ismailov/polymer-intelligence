import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { useCompanies } from "@/entities/company";
import { LoadingView } from "@/shared/ui";

/**
 * Registration gate: an account with no company is sent to the onboarding sheet.
 *
 * Every cabinet surface is company-scoped — offers, inquiries, requests, deals
 * and contracts all hang off the active company — so a companyless account has
 * nothing to look at, and letting it in produces a shell of empty states with no
 * way to fix any of them. Registration is the first thing after sign-in.
 *
 * A failed list query deliberately falls through rather than gating: a transient
 * 500 must not lock an existing customer out of their own cabinet.
 */
/**
 * What a technologist (0055) may open inside the shell. They are a private
 * person with no company, so every company-scoped page would be a row of empty
 * states — and "no company" is their finished state, not an unfinished
 * registration. Their own section plus the two account-level pages.
 */
const EXPERT_PATHS = ["/cabinet/expert", "/cabinet/notifications", "/cabinet/settings"];

export function RequireCompany() {
  const { t } = useTranslation();
  const isExpert = useAuthStore((s) => s.account?.applied_as === "technologist");
  const { pathname } = useLocation();
  const query = useCompanies(!isExpert);

  if (isExpert) {
    const allowed = EXPERT_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
    return allowed ? <Outlet /> : <Navigate to="/cabinet/expert" replace />;
  }

  // "Empty but revalidating" is loading, not "no companies": the registration
  // wizard mounts OUTSIDE this guard, so its invalidation of the list only
  // marks the cache stale — the refetch fires when this guard mounts. Judging
  // the stale pre-registration [] bounced a freshly registered account
  // straight back to onboarding.
  if (query.isLoading || (query.isFetching && (query.data?.length ?? 0) === 0)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <LoadingView label={t("common.loading")} />
      </div>
    );
  }

  if (query.data && query.data.length === 0) {
    return <Navigate to="/cabinet/onboarding" replace />;
  }

  return <Outlet />;
}
