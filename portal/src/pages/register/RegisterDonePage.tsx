import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { AuthLayout } from "@/pages/login";
import { Card, CardBody, SuccessMark } from "@/shared/ui";

/**
 * "We will be in touch."
 *
 * The honest end of the request flow: there is nothing more the visitor can do here,
 * and no code to wait for. Saying so plainly is the whole screen — the failure mode
 * to avoid is a page that looks like a half-finished sign-up and leaves someone
 * refreshing it waiting for an SMS that is never coming.
 */
export function RegisterDonePage() {
  const { t } = useTranslation();

  return (
    <AuthLayout title={t("register.doneTitle")}>
      <Card>
        <CardBody className="flex flex-col items-center gap-4 text-center">
          <SuccessMark size="lg" />
          <p className="text-sm text-text-muted">{t("register.doneBody")}</p>
          <p className="text-sm text-text-muted">{t("register.doneNext")}</p>
        </CardBody>
      </Card>

      <p className="text-center text-sm text-text-muted">
        <Link to="/" className="font-medium text-brand hover:underline">
          {t("register.backToMarket")}
        </Link>
      </p>
    </AuthLayout>
  );
}
