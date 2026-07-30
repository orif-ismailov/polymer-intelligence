import { useTranslation } from "react-i18next";

import { EmptyState, FileIcon } from "@/shared/ui";

/**
 * «Документы» — public document set does not exist yet. Do not surface private
 * verification downloads here.
 */
export function ProfileDocumentsTab() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={<FileIcon size={28} />}
      title={t("companyProfile.documentsEmpty")}
      description={t("companyProfile.documentsEmptyBody")}
    />
  );
}
