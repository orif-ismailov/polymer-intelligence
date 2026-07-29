import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useCompany } from "@/entities/company";
import { EimzoSignButton, companyIdentitySigner } from "@/features/eimzo-sign";
import { CaseStatusPanel } from "@/widgets/case-status-panel";
import { Alert, ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";
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
      <PageHeader
        backTo="/companies"
        backLabel={t("nav.companies")}
        title={t("verification.title")}
        subtitle={t("verification.subtitle", { company: displayName })}
        actions={
          <LinkButton variant="outline" to={`/companies/${company.id}`}>
            {t("company.detailsTitle")}
          </LinkButton>
        }
      />

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
            signer={companyIdentitySigner(company.id)}
            holderOf={(o) => o.holder_masked}
            onConfirmed={() => void query.refetch()}
          />
        </div>
      ) : null}

      <CaseStatusPanel companyId={company.id} fallbackCase={company.case ?? company.active_case} />
    </div>
  );
}
