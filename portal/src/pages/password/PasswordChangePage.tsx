import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { ChangePasswordForm } from "@/features/change-password";
import { AuthLayout } from "@/pages/login";
import { Card, CardBody } from "@/shared/ui";

/**
 * Set a new password.
 *
 * Two arrivals, one screen. A first-time visitor is sent here by
 * `RequirePasswordCurrent` because the password in their contract is an initial secret
 * and the API refuses every other route until it is replaced; anyone else came from
 * Settings by choice. The subtitle is the only difference, and it matters — being
 * moved somewhere you did not ask to go deserves a sentence saying why.
 */
export function PasswordChangePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const forced = useAuthStore((s) => s.account?.must_change_password ?? false);

  return (
    <AuthLayout
      title={t("password.title")}
      subtitle={forced ? t("password.forcedSubtitle") : t("password.subtitle")}
    >
      <Card>
        <CardBody>
          <ChangePasswordForm
            onChanged={() => void navigate("/cabinet", { replace: true })}
          />
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
