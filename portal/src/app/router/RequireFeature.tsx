import { useTranslation } from "react-i18next";
import { Navigate, Outlet } from "react-router-dom";

import { companyHasFeature, useActiveCompany, type FeatureKey } from "@/entities/company";
import { LoadingView } from "@/shared/ui";

/**
 * Role gate: a cabinet feature outside the active company's account type
 * silently redirects to the cabinet home — for a laboratory, «Предложения»
 * simply does not exist. The matrix lives in `entities/company/model/features.ts`
 * and the API enforces the same sets with 403 `role_not_allowed`.
 *
 * Waits on `isLoading` (RequestsRouteSwitch's reasoning: defaulting would flash
 * the wrong page), and fails OPEN on a query error — a transient 500 must not
 * shrink a customer's cabinet. Switching the active company re-evaluates this,
 * so a distributor→laboratory switch mid-page walks you home.
 */
export function RequireFeature({ feature }: { feature: FeatureKey }) {
  const { t } = useTranslation();
  const { activeCompany, isLoading, isError } = useActiveCompany();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <LoadingView label={t("common.loading")} />
      </div>
    );
  }

  if (!isError && activeCompany && !companyHasFeature(activeCompany, feature)) {
    return <Navigate to="/cabinet" replace />;
  }

  return <Outlet />;
}
