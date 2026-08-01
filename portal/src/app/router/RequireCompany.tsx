import { useTranslation } from "react-i18next";
import { Navigate, Outlet } from "react-router-dom";

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
export function RequireCompany() {
  const { t } = useTranslation();
  const query = useCompanies();

  if (query.isLoading) {
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
