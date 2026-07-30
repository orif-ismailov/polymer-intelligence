import { useTranslation } from "react-i18next";

import { EmptyState, StarIcon } from "@/shared/ui";

/** «Отзывы» — mockup chrome with an honest empty state until ratings exist. */
export function ProfileReviewsTab() {
  const { t } = useTranslation();
  return (
    <div className="space-y-4" data-testid="seller-profile-reviews">
      <div className="rounded-lg border border-border bg-surface px-4 py-5 text-center">
        <p className="flex items-center justify-center gap-1 text-2xl font-semibold text-text">
          <StarIcon size={22} className="text-gold" />
          {t("companyProfile.reviewsScorePending")}
        </p>
        <p className="mt-1 text-sm text-text-muted">{t("companyProfile.reviewsHint")}</p>
      </div>
      <EmptyState
        icon={<StarIcon size={28} />}
        title={t("companyProfile.reviewsEmpty")}
        description={t("companyProfile.reviewsEmptyBody")}
      />
    </div>
  );
}
