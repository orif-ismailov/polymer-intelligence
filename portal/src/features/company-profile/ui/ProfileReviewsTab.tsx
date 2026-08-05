import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import { Card, CardBody, EmptyState, StarIcon } from "@/shared/ui";

import type { CompanyProfileReview } from "../model/types";

interface ProfileReviewsTabProps {
  rating?: number | null;
  reviewCount?: number;
  reviews?: CompanyProfileReview[];
  /** Signed-in acting surface, mounted after hydration by the page. */
  action?: ReactNode;
}

/** Five stars with `filled` of them lit. */
function Stars({ filled }: { filled: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-hidden>
      {[1, 2, 3, 4, 5].map((i) => (
        <StarIcon
          key={i}
          size={14}
          className={i <= filled ? "text-gold" : "text-text-subtle"}
        />
      ))}
    </span>
  );
}

/**
 * «Отзывы» — the score, the published reviews, and (with a session) the form.
 *
 * The empty state is still here and still honest: a company nobody has reviewed
 * shows «оценка появится после сделок» rather than a zero, because those are
 * different statements and only one of them is true.
 *
 * Reviews arrive INLINE on the company payload rather than from a second call,
 * so this panel server-renders with content — `CompanyProfileView` mounts every
 * tab into the SSR HTML (`renderAllPanels`), and a fetch here would have put a
 * spinner in what a crawler reads.
 */
export function ProfileReviewsTab({
  rating,
  reviewCount = 0,
  reviews = [],
  action,
}: ProfileReviewsTabProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const rated = rating != null && reviewCount > 0;

  return (
    <div className="space-y-4" data-testid="seller-profile-reviews">
      <div className="rounded-lg border border-border bg-surface px-4 py-5 text-center">
        <p className="flex items-center justify-center gap-1.5 text-2xl font-semibold text-text">
          <StarIcon size={22} className="text-gold" />
          <span className="num">
            {rated ? rating.toFixed(1) : t("companyProfile.reviewsScorePending")}
          </span>
        </p>
        <p className="mt-1 text-sm text-text-muted">
          {rated
            ? t("companyProfile.reviewCount", { count: reviewCount })
            : t("companyProfile.reviewsHint")}
        </p>
      </div>

      {action}

      {reviews.length === 0 ? (
        <EmptyState
          icon={<StarIcon size={28} />}
          title={t("companyProfile.reviewsEmpty")}
          description={t("companyProfile.reviewsEmptyBody")}
        />
      ) : (
        <ul className="space-y-2">
          {reviews.map((review) => (
            <li key={review.id}>
              <Card>
                <CardBody className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium text-text">
                      {review.author_company_name ?? t("companyProfile.reviewAnonymous")}
                    </p>
                    <div className="flex items-center gap-2">
                      <Stars filled={review.rating} />
                      <span className="num text-xs text-text-muted">{review.rating}/5</span>
                    </div>
                  </div>
                  {review.body ? (
                    <p className="text-sm leading-relaxed text-text">{review.body}</p>
                  ) : null}
                  <p className="text-xs text-text-subtle">
                    {formatDate(review.created_at, lang)}
                  </p>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
