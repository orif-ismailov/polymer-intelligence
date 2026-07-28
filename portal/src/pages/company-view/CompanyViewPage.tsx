import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { CompanyStatusBadge, useCompany } from "@/entities/company";
import { Alert, Card, CardBody, ErrorView, LinkButton, LoadingView, Skeleton } from "@/shared/ui";
import { ApiError } from "@/shared/api";

import { BankSection } from "./sections/BankSection";
import { DocumentsSection } from "./sections/DocumentsSection";
import { LicensesSection } from "./sections/LicensesSection";
import { ProfileSection } from "./sections/ProfileSection";
import { RolesSection } from "./sections/RolesSection";

/** Company statuses in which profile/bank/doc mutations are still allowed. */
const EDITABLE_STATUSES = new Set(["draft", "pending_verification", "rejected"]);

export function CompanyViewPage() {
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
        {notFound ? <LinkButton to="/companies">{t("nav.companies")}</LinkButton> : null}
      </ErrorView>
    );
  }

  const company = query.data;
  if (!company) return null;

  const editable = EDITABLE_STATUSES.has(company.status);
  const name = company.legal_name ?? company.short_name ?? t("companies.noName");

  return (
    <div className="space-y-5">
      <Card>
        <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-text">{name}</h1>
              <CompanyStatusBadge status={company.status} />
            </div>
            <p className="mt-1 text-sm text-text-muted">
              {t("companies.taxId")}: {company.tax_id} · {company.public_id}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <LinkButton variant="outline" to={`/companies/${company.id}/verification`}>
              {t("company.goToVerification")}
            </LinkButton>
            {company.status === "verified" ? (
              <LinkButton to="/offers/new">{t("company.createOffer")}</LinkButton>
            ) : null}
          </div>
        </CardBody>
      </Card>

      {!editable ? <Alert tone="info">{t("company.notEditable")}</Alert> : null}

      <ProfileSection company={company} editable={editable} />
      <RolesSection company={company} />
      <BankSection company={company} editable={editable} />
      <DocumentsSection company={company} editable={editable} />
      <LicensesSection companyId={company.id} />
    </div>
  );
}
