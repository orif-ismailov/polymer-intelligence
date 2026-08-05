import { useTranslation } from "react-i18next";

import { Card, CardBody } from "@/shared/ui";

/**
 * The two tabs that exist as chrome.
 *
 * The mockup's rail has five entries and the surfaces behind two of them are
 * not built yet. They are shared rather than copied into each tier so the empty
 * states cannot drift apart while nobody is looking at them.
 */
export function OfferCompatibilityPanel() {
  const { t } = useTranslation();
  return (
    <Card className="border-info/40">
      <CardBody className="space-y-2">
        <p className="text-sm font-medium text-text">{t("market.detail.compatibility")}</p>
        <p className="text-sm text-text-muted">{t("market.detail.compatibilityBody")}</p>
        <p className="text-xs text-text-subtle">{t("market.detail.comingSoon")}</p>
      </CardBody>
    </Card>
  );
}

export function OfferReviewsPanel() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardBody>
        <p className="text-sm text-text-muted">{t("market.detail.reviewsEmpty")}</p>
      </CardBody>
    </Card>
  );
}
