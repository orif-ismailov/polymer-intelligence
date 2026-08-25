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
        {notFound ? <LinkButton to="/cabinet/companies">{t("nav.companies")}</LinkButton> : null}
      </ErrorView>
    );
  }

  const company = query.data;
  if (!company) return null;

  const displayName = company.legal_name ?? company.short_name ?? company.tax_id;
  /**
   * Offered until the identity IS confirmed — not only while the company is
   * still being verified.
   *
   * The status gate came from the original flow, where signing happened during
   * registration. It left every company verified before the Didox rail existed
   * permanently unable to confirm a signer — and `Owner.FizTin`/`Fio` are
   * mandatory on a «Договор НК», so those companies could never send one. The
   * backend never had the restriction: it gates on the certificate's INN
   * matching the company, which is the rule that actually protects anything.
   */
  const canSignEimzo = !company.identity_locked;

  return (
    <div className="space-y-5">
      <PageHeader
        backTo="/cabinet/companies"
        backLabel={t("nav.companies")}
        title={t("verification.title")}
        subtitle={t("verification.subtitle", { company: displayName })}
        actions={
          <LinkButton variant="outline" to={`/cabinet/companies/${company.id}`}>
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
