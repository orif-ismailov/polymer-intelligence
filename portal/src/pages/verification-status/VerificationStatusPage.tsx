import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useCompany } from "@/entities/company";
import { EimzoSignButton } from "@/features/eimzo-sign";
import { CaseStatusPanel } from "@/widgets/case-status-panel";
import { Alert, ErrorView, LinkButton, LoadingView } from "@/shared/ui";
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
  const canSignEimzo =
    !company.identity_locked &&
    (company.status === "draft" || company.status === "pending_verification");

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

      {company.identity_locked ? (
        <Alert tone="success" title={t("eimzo.confirmedBadge")}>
          <span data-testid="eimzo-confirmed">
            {t("eimzo.confirmedBody", {
              name: company.director_name ?? displayName,
            })}
          </span>
        </Alert>
      ) : canSignEimzo ? (
        <div
          className="flex flex-col gap-2 rounded-md border border-dashed border-border bg-surface-2/40 p-4 sm:flex-row sm:items-center sm:justify-between"
          data-testid="eimzo-offer"
        >
          <div>
            <p className="text-sm font-medium text-text">{t("eimzo.offerTitle")}</p>
            <p className="mt-0.5 text-xs text-text-muted">{t("eimzo.offerBody")}</p>
          </div>
          <EimzoSignButton
            companyId={company.id}
            onConfirmed={() => void query.refetch()}
          />
        </div>
      ) : null}

      <CaseStatusPanel companyId={company.id} fallbackCase={company.case ?? company.active_case} />
    </div>
  );
}
