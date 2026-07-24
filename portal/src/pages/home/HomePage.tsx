import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { CompanyStatusBadge, useActiveCompany } from "@/entities/company";
import { CaseStatusBadge } from "@/entities/verification";
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  LinkButton,
  LoadingView,
} from "@/shared/ui";

interface QuickCardProps {
  to: string;
  title: string;
  hint: string;
}

function QuickCard({ to, title, hint }: QuickCardProps) {
  return (
    <Link
      to={to}
      className="block rounded-lg border border-border bg-surface p-5 transition-colors hover:border-brand-line hover:bg-surface-2"
    >
      <p className="text-base font-semibold text-text">{title}</p>
      <p className="mt-1 text-sm text-text-muted">{hint}</p>
    </Link>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  const account = useAuthStore((s) => s.account);
  const { activeCompany, isLoading } = useActiveCompany();

  const greeting = account?.name
    ? t("home.welcome", { name: account.name })
    : t("home.welcomeAnon");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{greeting}</h1>
        <p className="mt-1 text-sm text-text-muted">{t("home.title")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <QuickCard to="/companies" title={t("home.companiesCard")} hint={t("home.companiesCardHint")} />
        <QuickCard to="/offers" title={t("home.offersCard")} hint={t("home.offersCardHint")} />
      </div>

      {isLoading ? (
        <LoadingView />
      ) : activeCompany ? (
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>{t("home.activeCompany")}</CardTitle>
            <CompanyStatusBadge status={activeCompany.status} />
          </CardHeader>
          <CardBody className="space-y-4">
            <div>
              <p className="text-lg font-medium text-text">
                {activeCompany.legal_name ?? activeCompany.short_name ?? t("companies.noName")}
              </p>
              <p className="text-sm text-text-muted">
                {t("companies.taxId")}: {activeCompany.tax_id}
              </p>
            </div>

            {activeCompany.active_case ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-text-muted">{t("home.verificationState")}:</span>
                <CaseStatusBadge status={activeCompany.active_case.status} />
              </div>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <LinkButton variant="outline" to={`/companies/${activeCompany.id}`}>
                {t("companies.open")}
              </LinkButton>
              <LinkButton variant="outline" to={`/companies/${activeCompany.id}/verification`}>
                {t("home.goToVerification")}
              </LinkButton>
              {activeCompany.status === "verified" ? (
                <LinkButton to="/offers/new">{t("home.publishOffer")}</LinkButton>
              ) : null}
            </div>
          </CardBody>
        </Card>
      ) : (
        <EmptyState
          title={t("home.noActiveCompany")}
          description={t("home.noActiveCompanyBody")}
          action={<LinkButton to="/companies/new/1">{t("home.createCompany")}</LinkButton>}
        />
      )}
    </div>
  );
}
