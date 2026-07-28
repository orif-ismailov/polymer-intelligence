import { useTranslation } from "react-i18next";

import { useAuthStore } from "@/entities/account";
import { useCompanyLicenses } from "@/entities/compliance";
import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import { Badge, Card, CardBody, CardHeader, CardTitle, Skeleton } from "@/shared/ui";

/**
 * Licences the company holds, per regime.
 *
 * Read-only on purpose: a licence is registered by staff from the document the
 * company uploaded and they accepted. Letting a company declare its own licence
 * here would make the publish gate self-certified, which is the one thing it
 * must not be.
 */
export function LicensesSection({ companyId }: { companyId: number }) {
  const { t } = useTranslation();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const query = useCompanyLicenses(companyId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("compliance.licenses")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-sm text-text-muted">{t("compliance.licensesHint")}</p>

        {query.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : query.data && query.data.length > 0 ? (
          <ul className="divide-y divide-border">
            {query.data.map((licence) => (
              <li key={licence.id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="text-sm font-medium text-text">
                  {t(`compliance.regime.${licence.regime}`)}
                </span>
                {licence.license_number ? (
                  <span className="num text-sm text-text-muted">{licence.license_number}</span>
                ) : null}
                {licence.expires_at ? (
                  <span className="text-sm text-text-muted">
                    {t("compliance.until")} {formatDate(licence.expires_at, lang)}
                  </span>
                ) : null}
                <Badge tone={licence.is_active ? "success" : "neutral"} className="ml-auto">
                  {licence.is_active
                    ? t("compliance.licenseActive")
                    : t(`compliance.licenseStatus.${licence.status}`)}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">{t("compliance.noLicenses")}</p>
        )}
      </CardBody>
    </Card>
  );
}
