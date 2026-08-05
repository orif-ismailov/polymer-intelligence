import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { CompanyStatusBadge, useCompany } from "@/entities/company";
import { ApiError } from "@/shared/api";
import {
  Alert,
  ErrorView,
  LinkButton,
  LoadingView,
  PageHeader,
  Skeleton,
} from "@/shared/ui";

import { BankSection } from "./sections/BankSection";
import { DocumentsSection } from "./sections/DocumentsSection";
import { LicensesSection } from "./sections/LicensesSection";
import { ProfileSection } from "./sections/ProfileSection";
import { RolesSection } from "./sections/RolesSection";
import { StorefrontSection } from "./sections/StorefrontSection";

/** Company statuses in which profile/bank/doc mutations are still allowed. */
const EDITABLE_STATUSES = new Set(["draft", "pending_verification", "rejected"]);

/**
 * Owner-only registry editor (bank, docs, roles, licenses).
 *
 * The public-facing sheet lives at `/cabinet/companies/:id` via `CompanyProfileView`;
 * this route is the place to mutate registry fields.
 */
export function CompanyManagePage() {
  const { t } = useTranslation();
  const params = useParams<{ companyId: string }>();
  const companyId = Number(params.companyId);
  const query = useCompany(Number.isInteger(companyId) ? companyId : null);

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <LoadingView />
      </div>
    );
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <ErrorView
        title={notFound ? t("errors.notFound") : t("errors.loadFailed")}
        message={notFound ? t("errors.notFoundBody") : undefined}
        retryLabel={notFound ? undefined : t("common.retry")}
        onRetry={notFound ? undefined : () => void query.refetch()}
      >
        {notFound ? <LinkButton to="/cabinet/companies">{t("nav.companies")}</LinkButton> : null}
      </ErrorView>
    );
  }

  const company = query.data;
  if (!company) return null;

  const editable = EDITABLE_STATUSES.has(company.status);
  const name = company.legal_name ?? company.short_name ?? t("companies.noName");
  const isVerified = company.status === "verified";
  const isCarrier = company.roles.some((r) => r.role === "logistics_provider");

  return (
    <div className="space-y-5">
      <PageHeader
        backTo={isVerified ? `/cabinet/companies/${company.id}` : "/cabinet/companies"}
        backLabel={isVerified ? t("companyProfile.title") : t("nav.companies")}
        title={name}
        subtitle={`${t("companies.taxId")}: ${company.tax_id}`}
        badge={<CompanyStatusBadge status={company.status} />}
        actions={
          <>
            <LinkButton variant="outline" to={`/cabinet/companies/${company.id}/verification`}>
              {t("company.goToVerification")}
            </LinkButton>
            {isVerified ? (
              <LinkButton to="/cabinet/offers/new">{t("company.createOffer")}</LinkButton>
            ) : null}
          </>
        }
      />

      {!editable ? <Alert tone="info">{t("company.notEditable")}</Alert> : null}

      <ProfileSection company={company} editable={editable} />
      {/* Storefront copy, and NOT behind `editable` — see the note in the
          section: a carrier reaches the public directory only once verified,
          which is the state that flag closes. */}
      {isCarrier ? <StorefrontSection company={company} /> : null}
      <RolesSection company={company} />
      <BankSection company={company} editable={editable} />
      <DocumentsSection company={company} editable={editable} />
      <LicensesSection companyId={company.id} />
    </div>
  );
}
