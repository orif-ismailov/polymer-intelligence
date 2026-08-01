import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useCompanies } from "@/entities/company";
import { usePublicCompanyProfile } from "@/entities/market";
import { CabinetCompanyProfile } from "@/features/company-profile";
import { ApiError } from "@/shared/api";
import {
  Button,
  ErrorView,
  LinkButton,
  LoadingView,
  StickyActionBar,
} from "@/shared/ui";

import { CompanyManagePage } from "./CompanyManagePage";

/**
 * `/cabinet/companies/:id` — same public profile sheet as `/cabinet/sellers/:id` when the
 * company is verified. Draft / pending members fall through to the manage
 * editor (nothing public to show yet).
 */
export function CompanyViewPage() {
  const { t } = useTranslation();
  const params = useParams<{ companyId: string }>();
  const companyId = Number(params.companyId);
  const validId = Number.isInteger(companyId) ? companyId : null;

  const publicQuery = usePublicCompanyProfile(validId);
  const companiesQuery = useCompanies();
  const isMember =
    validId != null && companiesQuery.data?.some((c) => c.id === validId) === true;

  if (validId == null) {
    return (
      <ErrorView title={t("errors.notFound")} message={t("errors.notFoundBody")}>
        <LinkButton to="/cabinet/companies">{t("nav.companies")}</LinkButton>
      </ErrorView>
    );
  }

  if (publicQuery.isLoading || companiesQuery.isLoading) {
    return <LoadingView label={t("common.loading")} />;
  }

  if (publicQuery.isSuccess && publicQuery.data) {
    return (
      <CabinetCompanyProfile
        companyId={validId}
        backTo="/cabinet/companies"
        ownerActions={
          isMember ? (
            <StickyActionBar>
              <div className="flex w-full flex-wrap gap-2" data-testid="company-owner-actions">
                <LinkButton
                  variant="outline"
                  size="lg"
                  className="min-w-0 flex-1"
                  to={`/cabinet/companies/${validId}/manage`}
                >
                  {t("company.manage")}
                </LinkButton>
                <LinkButton
                  variant="outline"
                  size="lg"
                  className="min-w-0 flex-1"
                  to={`/cabinet/companies/${validId}/verification`}
                >
                  {t("company.goToVerification")}
                </LinkButton>
                <LinkButton size="lg" className="min-w-0 flex-[1.4]" to="/cabinet/offers/new">
                  {t("company.createOffer")}
                </LinkButton>
              </div>
            </StickyActionBar>
          ) : undefined
        }
      />
    );
  }

  // Public profile 404 — member of a not-yet-verified company → manage editor.
  if (isMember) {
    return <CompanyManagePage />;
  }

  const notFound =
    publicQuery.error instanceof ApiError && publicQuery.error.status === 404;

  return (
    <ErrorView
      title={notFound ? t("companyProfile.notFound") : t("errors.loadFailed")}
      message={notFound ? t("errors.notFoundBody") : undefined}
      retryLabel={notFound ? undefined : t("common.retry")}
      onRetry={notFound ? undefined : () => void publicQuery.refetch()}
    >
      {notFound ? (
        <LinkButton to="/cabinet/companies">{t("nav.companies")}</LinkButton>
      ) : (
        <Button variant="outline" onClick={() => void publicQuery.refetch()}>
          {t("common.retry")}
        </Button>
      )}
    </ErrorView>
  );
}
