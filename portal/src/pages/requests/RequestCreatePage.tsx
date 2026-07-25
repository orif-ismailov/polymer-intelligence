import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { RequestWizard } from "@/features/request-wizard";
import { EmptyState, LinkButton } from "@/shared/ui";

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
    <div className="space-y-6">
      <div>
        <LinkButton to="/requests" variant="ghost" className="text-sm">
          ← {t("requests.title")}
        </LinkButton>
        <h1 className="mt-2 text-2xl font-semibold text-text">{t("requests.create")}</h1>
        <p className="mt-1 text-sm text-text-muted">
          {t("requests.forCompany", { company: companyName })}
        </p>
      </div>
      <RequestWizard
        companyId={activeCompany.id}
        companyName={companyName}
        onCreated={(id) => navigate(`/requests/${id}`)}
      />
    </div>
  );
}
