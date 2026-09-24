import { useTranslation } from "react-i18next";

import { StarIcon } from "@/shared/ui";

/** «★ 4.9 · 12 отзывов», or «Нет отзывов» — never a fake zero. */
export function TechnologistRating({
  avg,
  count,
}: {
  avg: string | null;
  count: number;
}) {
  const { t } = useTranslation();
  if (!avg || count === 0) {
    return <span className="text-xs text-text-subtle">{t("technologists.noReviews")}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-text">
      <StarIcon size={14} className="text-gold" />
      <span className="num font-semibold">{Number(avg).toFixed(1)}</span>
      <span className="text-text-subtle">· {t("technologists.reviews", { count })}</span>
    </span>
  );
}
