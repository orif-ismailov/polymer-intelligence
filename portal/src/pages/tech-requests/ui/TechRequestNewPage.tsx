import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { TechRequestForm } from "@/features/tech-request-form";
import { ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/** `/cabinet/tech-requests/new` — «Найти технолога». */
export function TechRequestNewPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany, isLoading } = useActiveCompany();

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <PageHeader
        backTo="/cabinet/tech-requests"
        backLabel={t("techRequest.listTitle")}
        title={t("techRequest.newTitle")}
        subtitle={t("techRequest.newSubtitle")}
      />
      <div className="mt-5">
        <TechRequestForm
          companyId={activeCompany.id}
          onCreated={(id) => navigate(`/cabinet/tech-requests/${id}`, { replace: true })}
        />
      </div>
    </div>
  );
}
