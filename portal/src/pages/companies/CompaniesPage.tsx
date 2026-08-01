import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { CompanyStatusBadge, useCompanies } from "@/entities/company";
import type { CompanySummary } from "@/entities/company";
import { CaseStatusBadge } from "@/entities/verification";
import { coerceLang, useEnumLabels } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import {
  Card,
  ChevronRightIcon,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  RegistryIcon,
} from "@/shared/ui";

function CompanyRow({ company, lang }: { company: CompanySummary; lang: string }) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const name = company.legal_name ?? company.short_name ?? t("companies.noName");
  /** Compare what the badges would SAY, not the enum values — they differ. */
  const sameLabel = (companyStatus: string, caseStatus: string): boolean =>
    label("companyStatus", companyStatus) === label("caseStatus", caseStatus);
  return (
    <Link
      to={`/cabinet/companies/${company.id}`}
      className="flex items-center justify-between gap-4 border-b border-border px-5 py-4 last:border-b-0 hover:bg-surface-2"
    >
      <div className="min-w-0">
        <p className="truncate font-medium text-text">{name}</p>
        {/* The public_id used to be appended here. It is an opaque UUID that means
            nothing to the person reading the list, it pushed the STIR they DO
            recognise onto a second line, and the company card already shows it
            once under «Публичный ID» for support to quote. */}
        <p className="num mt-0.5 text-sm text-text-muted">
          {t("companies.taxId")}: {company.tax_id}
        </p>
        {company.verified_at ? (
          <p className="num mt-0.5 text-xs text-text-subtle">
            {t("companies.verifiedAt")}: {formatDate(company.verified_at, lang)}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <div className="flex flex-col items-end gap-1.5">
          <CompanyStatusBadge status={company.status} />
          {/* Only when it adds something. A draft company has a draft case, and both
              labels are «Черновик», so the card stacked the same word twice and read
              like a rendering bug. */}
          {company.active_case && !sameLabel(company.status, company.active_case.status) ? (
            <CaseStatusBadge status={company.active_case.status} />
          ) : null}
        </div>
        <span className="text-text-subtle">
          <ChevronRightIcon size={16} />
        </span>
      </div>
    </Link>
  );
}

export function CompaniesPage() {
  const { t } = useTranslation();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const query = useCompanies();

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("companies.title")}
        subtitle={t("companies.subtitle")}
        actions={
          (query.data?.length ?? 0) > 0 ? (
            <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
          ) : null
        }
      />

      {query.isLoading ? (
        <Card>
          <div className="space-y-3 p-5">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        </Card>
      ) : query.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void query.refetch()}
        />
      ) : query.data && query.data.length > 0 ? (
        <Card className="overflow-hidden">
          {query.data.map((company) => (
            <CompanyRow key={company.id} company={company} lang={lang} />
          ))}
        </Card>
      ) : (
        <EmptyState
          icon={<RegistryIcon size={28} />}
          title={t("companies.empty")}
          description={t("companies.emptyBody")}
          action={<LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>}
        />
      )}
    </div>
  );
}
