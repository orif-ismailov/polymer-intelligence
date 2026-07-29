import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { RequestWizard } from "@/features/request-wizard";
import {
  EmptyState,
  PageHeader,
} from "@/shared/ui";

export function RequestCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();

  if (!activeCompany) {
    return (
      <EmptyState title={t("home.noActiveCompany")} description={t("home.noActiveCompanyBody")} />
    );
  }

  const companyName =
    activeCompany.short_name ?? activeCompany.legal_name ?? activeCompany.tax_id;

  return (
    <div className="space-y-5">
      <PageHeader
        backTo="/requests"
        backLabel={t("requests.title")}
        title={t("requests.create")}
        subtitle={t("requests.forCompany", { company: companyName })}
      />
      <RequestWizard
        companyId={activeCompany.id}
        companyName={companyName}
        onCreated={(id) => navigate(`/requests/${id}`)}
      />
    </div>
  );
}
