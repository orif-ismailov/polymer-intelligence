import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useCompany } from "@/entities/company";
import { CaseStatusPanel } from "@/widgets/case-status-panel";
import { ErrorView, LinkButton, LoadingView } from "@/shared/ui";
import { ApiError } from "@/shared/api";

export function VerificationStatusPage() {
  const { t } = useTranslation();
  const params = useParams<{ companyId: string }>();
  const companyId = Number(params.companyId);
  const valid = Number.isInteger(companyId);
  const query = useCompany(valid ? companyId : null);

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;

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

  const displayName = company.legal_name ?? company.short_name ?? company.tax_id;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">{t("verification.title")}</h1>
          <p className="mt-1 text-sm text-text-muted">
            {t("verification.subtitle", { company: displayName })}
          </p>
        </div>
        <LinkButton variant="outline" to={`/companies/${company.id}`}>
          {t("company.detailsTitle")}
        </LinkButton>
      </div>

      <CaseStatusPanel companyId={company.id} fallbackCase={company.case ?? company.active_case} />
    </div>
  );
}
