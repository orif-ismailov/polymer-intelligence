import { useTranslation } from "react-i18next";

import {
  Card,
  CardBody,
  LinkButton,
  PageHeader,
} from "@/shared/ui";

interface OffersLockedProps {
  companyId: number;
  companyName: string;
}

/**
 * Locked state shown when the active company is not verified. Mirrors the
 * backend's 403 `company_not_verified` guard so the UI never lets the user
 * reach a form that would be rejected.
 */
export function OffersLocked({ companyId, companyName }: OffersLockedProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-5">
      <PageHeader
        title={t("offers.title")}
        subtitle={t("offers.subtitle", { company: companyName })}
      />

      <Card>
        <CardBody className="flex flex-col items-center gap-4 py-10 text-center">
          <span
            aria-hidden="true"
            className="flex h-12 w-12 items-center justify-center rounded-full bg-warning/10 text-warning"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.6" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </span>
          <div>
            <h2 className="text-lg font-semibold text-text">{t("offers.lockedTitle")}</h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-text-muted">{t("offers.lockedBody")}</p>
          </div>
          <LinkButton to={`/companies/${companyId}/verification`}>
            {t("offers.goToVerification")}
          </LinkButton>
        </CardBody>
      </Card>
    </div>
  );
}
