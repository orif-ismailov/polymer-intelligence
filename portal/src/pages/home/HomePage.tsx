import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { CompanyStatusBadge, useActiveCompany } from "@/entities/company";
import { useNewsArticles } from "@/entities/news";
import { useUnreadCount } from "@/entities/notification";
import { useRequests } from "@/entities/request";
import { CaseStatusBadge } from "@/entities/verification";
import {
  Building2,
  ClipboardList,
  Factory,
  Handshake,
  Inbox,
  Package,
  Store,
} from "lucide-react";
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ChevronRightIcon,
  EmptyState,
  LinkButton,
  LoadingView,
  RegistryIcon,
  PageHeader,
  StatChip,
} from "@/shared/ui";

const ACTIVE_REQUEST_STATUSES = new Set(["new", "viewed", "in_progress", "offer_sent"]);

/**
 * The mockups' module tile: a bordered card with the destination and a one-line
 * explanation. Only routes that already exist in the cabinet — the sheet's other
 * eight modules belong to features we haven't built.
 */
function ModuleCard({
  to,
  title,
  hint,
  icon,
}: {
  to: string;
  title: string;
  hint: string;
  icon: ReactNode;
}) {
  return (
    <Link
      to={to}
      className="group flex items-start justify-between gap-3 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-brand-line hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
    >
      <span className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 shrink-0 text-brand">{icon}</span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-text">{title}</span>
          <span className="mt-0.5 block text-xs text-text-muted">{hint}</span>
        </span>
      </span>
      <span className="mt-0.5 shrink-0 text-text-subtle transition-colors group-hover:text-brand">
        <ChevronRightIcon size={16} />
      </span>
    </Link>
  );
}

function SectionCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader action={action}>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">{children}</CardBody>
    </Card>
  );
}

export function HomePage() {
  const { t, i18n } = useTranslation();
  const account = useAuthStore((s) => s.account);
  const { activeCompany, isLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;

  const requests = useRequests(companyId);
  const unread = useUnreadCount();
  const news = useNewsArticles({ lang: i18n.language });

  const activeRequests =
    requests.data?.filter((r) => ACTIVE_REQUEST_STATUSES.has(r.status)).length ?? 0;
  const unreadCount = unread.data?.count ?? 0;
  const latestNews = (news.data ?? []).slice(0, 3);

  const greeting = account?.name
    ? t("home.welcome", { name: account.name })
    : t("home.welcomeAnon");

  return (
    <div className="space-y-5">
      <PageHeader title={greeting} subtitle={t("home.title")} />

      {/* Two real figures. The sheet's other tiles are metrics we don't have —
          a navigation link is not a metric, so those became module cards. */}
      <div className="grid grid-cols-2 gap-3">
        <StatChip value={activeRequests} label={t("home.activeRequests")} tone="brand" />
        <StatChip value={unreadCount} label={t("home.unread")} />
      </div>

      {isLoading ? (
        <LoadingView />
      ) : activeCompany ? (
        <SectionCard
          title={t("home.activeCompany")}
          action={<CompanyStatusBadge status={activeCompany.status} />}
        >
          <div>
            <p className="text-base font-medium text-text">
              {activeCompany.legal_name ?? activeCompany.short_name ?? t("companies.noName")}
            </p>
            <p className="num mt-0.5 text-sm text-text-muted">
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
            <LinkButton variant="outline" to={`/cabinet/companies/${activeCompany.id}`}>
              {t("companies.open")}
            </LinkButton>
            <LinkButton variant="outline" to={`/cabinet/companies/${activeCompany.id}/verification`}>
              {t("home.goToVerification")}
            </LinkButton>
            {activeCompany.status === "verified" ? (
              <LinkButton to="/cabinet/offers/new">{t("home.publishOffer")}</LinkButton>
            ) : null}
          </div>
        </SectionCard>
      ) : (
        <EmptyState
          title={t("home.noActiveCompany")}
          description={t("home.noActiveCompanyBody")}
          icon={<RegistryIcon size={28} />}
          action={<LinkButton to="/cabinet/companies/new/1">{t("home.createCompany")}</LinkButton>}
        />
      )}

      {/* The sheet's module grid, filled with the destinations this cabinet has. */}
      <section className="space-y-3">
        <h2 className="text-base font-semibold text-text">{t("home.quickActions")}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <ModuleCard
            to="/cabinet/market"
            title={t("nav.market")}
            hint={t("market.subtitle")}
            icon={<Store size={18} strokeWidth={1.75} aria-hidden />}
          />
          <ModuleCard
            to="/cabinet/manufacturers"
            title={t("nav.manufacturers")}
            hint={t("manufacturers.subtitle")}
            icon={<Factory size={18} strokeWidth={1.75} aria-hidden />}
          />
          <ModuleCard
            to="/cabinet/requests"
            title={t("nav.requests")}
            hint={t("requests.subtitle")}
            icon={<ClipboardList size={18} strokeWidth={1.75} aria-hidden />}
          />
          <ModuleCard
            to="/cabinet/inquiries"
            title={t("nav.inquiries")}
            hint={t("inquiries.subtitle")}
            icon={<Inbox size={18} strokeWidth={1.75} aria-hidden />}
          />
          <ModuleCard
            to="/cabinet/deals"
            title={t("nav.deals")}
            hint={t("deals.subtitle")}
            icon={<Handshake size={18} strokeWidth={1.75} aria-hidden />}
          />
          <ModuleCard
            to="/cabinet/companies"
            title={t("home.companiesCard")}
            hint={t("home.companiesCardHint")}
            icon={<Building2 size={18} strokeWidth={1.75} aria-hidden />}
          />
          <ModuleCard
            to="/cabinet/offers"
            title={t("home.offersCard")}
            hint={t("home.offersCardHint")}
            icon={<Package size={18} strokeWidth={1.75} aria-hidden />}
          />
        </div>
      </section>

      {latestNews.length > 0 ? (
        <SectionCard
          title={t("home.latestNews")}
          action={
            <Link to="/cabinet/news" className="text-sm text-brand hover:underline">
              {t("notifications.viewAll")}
            </Link>
          }
        >
          <div className="space-y-2">
            {latestNews.map((a) => (
              <Link
                key={a.id}
                to={`/cabinet/news/${a.id}`}
                className="block rounded-md border border-border px-3 py-2 text-sm transition-colors hover:border-brand-line hover:bg-surface-2"
              >
                {a.headline}
              </Link>
            ))}
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
