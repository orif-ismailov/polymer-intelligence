import { useTranslation } from "react-i18next";

import type { CompanyDetail } from "@/entities/company";
import { useEnumLabels } from "@/shared/i18n";
import { Badge, Card, CardBody, CardHeader, CardTitle } from "@/shared/ui";

interface RolesSectionProps {
  company: CompanyDetail;
}

export function RolesSection({ company }: RolesSectionProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company.roles")}</CardTitle>
      </CardHeader>
      <CardBody>
        {company.roles.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {company.roles.map((role) => (
              <Badge key={role.role} tone={role.status === "confirmed" ? "success" : "neutral"}>
                {label("businessRole", role.role)}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-muted">{t("common.notSpecified")}</p>
        )}
      </CardBody>
    </Card>
  );
}
