import { useTranslation } from "react-i18next";

import {
  Card,
  CardBody,
  LinkButton,
  LockIcon,
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
            <LockIcon size={24} />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-text">{t("offers.lockedTitle")}</h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-text-muted">{t("offers.lockedBody")}</p>
          </div>
          <LinkButton to={`/cabinet/companies/${companyId}/verification`}>
            {t("offers.goToVerification")}
          </LinkButton>
        </CardBody>
      </Card>
    </div>
  );
}
