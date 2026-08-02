import { useState } from "react";

import { useTranslation } from "react-i18next";

import { useSubmitCompanyReview } from "@/entities/company";
import {
  Alert,
  Button,
  Card,
  CardBody,
  FormField,
  StarIcon,
  Textarea,
} from "@/shared/ui";

interface ReviewFormProps {
  /** The company being reviewed. */
  companyId: number;
  /** The author's acting company. */
  authorCompanyId: number;
  onSubmitted: () => void;
}

/**
 * «Оставить отзыв» — one to five stars and an optional note.
 *
 * Re-submitting REPLACES the author company's existing review rather than being
 * refused: a review is a standing opinion per counterparty, so a second one is
 * an edit. The backend upserts for the same reason, which is why there is no
 * "you already reviewed" error to handle here.
 */
export function ReviewForm({ companyId, authorCompanyId, onSubmitted }: ReviewFormProps) {
  const { t } = useTranslation();
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [touched, setTouched] = useState(false);
  const submit = useSubmitCompanyReview(companyId);

  const ERRORS: Record<string, string> = {
    self_review: t("companyProfile.reviewErrors.self"),
  };
  const error = submit.error
    ? (ERRORS[submit.error.code ?? ""] ?? t("errors.generic"))
    : null;

  return (
    <Card>
      <CardBody className="space-y-4">
        <h3 className="text-sm font-semibold text-text">{t("companyProfile.reviewTitle")}</h3>

        <FormField
          label={t("companyProfile.reviewRating")}
          required
          error={touched && rating === 0 ? t("companyProfile.reviewErrors.ratingRequired") : null}
        >
          {() => (
            <div className="flex items-center gap-1" role="radiogroup" aria-label={t("companyProfile.reviewRating")}>
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={rating === value}
                  aria-label={String(value)}
                  className="rounded-sm p-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  onClick={() => setRating(value)}
                  data-testid={`review-star-${value}`}
                >
                  <StarIcon
                    size={24}
                    className={value <= rating ? "text-gold" : "text-text-subtle"}
                  />
                </button>
              ))}
            </div>
          )}
        </FormField>

        <FormField label={t("companyProfile.reviewBody")}>
          {({ id }) => (
            <Textarea
              id={id}
              rows={3}
              value={body}
              placeholder={t("companyProfile.reviewBodyPlaceholder")}
              onChange={(e) => setBody(e.target.value)}
            />
          )}
        </FormField>

        {error ? (
          <Alert tone="danger" title={t("errors.generic")}>
            {error}
          </Alert>
        ) : null}

        <Button
          loading={submit.isPending}
          data-testid="review-submit"
          onClick={() => {
            setTouched(true);
            if (rating === 0) return;
            submit.mutate(
              { company_id: authorCompanyId, rating, body: body.trim() || null },
              { onSuccess: onSubmitted },
            );
          }}
        >
          {t("companyProfile.reviewSubmit")}
        </Button>
      </CardBody>
    </Card>
  );
}
