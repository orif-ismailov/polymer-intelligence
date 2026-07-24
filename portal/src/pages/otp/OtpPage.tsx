import { useEffect } from "react";

import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";

import { OtpForm } from "@/features/auth-by-otp";
import { AuthLayout } from "@/pages/login/AuthLayout";
import { useAuthFlowStore } from "@/pages/login";
import { Card, CardBody } from "@/shared/ui";

/** OTP code entry screen — step 2 of the login flow. */
export function OtpPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const phone = useAuthFlowStore((s) => s.phone);
  const cooldownSeconds = useAuthFlowStore((s) => s.cooldownSeconds);
  const clear = useAuthFlowStore((s) => s.clear);

  // Clear the pending phone when leaving the screen.
  useEffect(() => () => clear(), [clear]);

  // Guard: no pending phone (e.g. direct navigation / reload) → back to /login.
  if (!phone) {
    return <Navigate to="/login" replace />;
  }

  return (
    <AuthLayout title={t("auth.codeTitle")} subtitle={t("auth.loginSubtitle")}>
      <Card>
        <CardBody>
          <OtpForm
            phone={phone}
            initialCooldown={cooldownSeconds}
            onVerified={() => navigate("/", { replace: true })}
            onChangePhone={() => navigate("/login", { replace: true })}
          />
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
