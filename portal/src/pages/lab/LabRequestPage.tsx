import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { LabRequestForm } from "@/features/lab-request";
import { ErrorView, LinkButton, LoadingView, PageHeader } from "@/shared/ui";

/**
 * `/cabinet/lab/requests/new` — «Новая заявка» на исследование.
 *
 * A cabinet route rather than a slot on a lab's public profile: the sheet has
 * its own chrome, `RequireAuth` + `RequireCompany` already are the gate this flow
 * needs, and the public profile's HTML is shared-cached (`s-maxage=60`), so
 * anything mounted there must be proven never to reach the anonymous render.
 *
 * No laboratory in the path — the request is broadcast to all of them.
 */
export function LabRequestPage() {
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
        backTo="/cabinet/lab"
        backLabel={t("labRequest.myRequests")}
        title={t("labRequest.title")}
        subtitle={t("labRequest.broadcastHint")}
      />
      <div className="mt-5">
        <LabRequestForm
          companyId={activeCompany.id}
          onSent={(requestId) =>
            navigate(`/cabinet/lab/requests/${requestId}/done`, { replace: true })
          }
        />
      </div>
    </div>
  );
}
