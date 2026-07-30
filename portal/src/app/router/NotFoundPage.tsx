import { useTranslation } from "react-i18next";

import { EmptyState, LinkButton, AlertCircleIcon } from "@/shared/ui";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="py-16">
      <EmptyState
          icon={<AlertCircleIcon size={28} />}
        title={t("errors.notFound")}
        description={t("errors.notFoundBody")}
        action={<LinkButton to="/">{t("nav.home")}</LinkButton>}
      />
    </div>
  );
}
