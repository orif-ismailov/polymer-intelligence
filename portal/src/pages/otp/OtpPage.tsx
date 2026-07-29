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

  // Guard: no pending phone (e.g. direct navigation / reload) → back to /login.
  // NB: the pending phone is intentionally NOT cleared on unmount — a React 18
  // StrictMode mount→cleanup→mount would null it during mount and bounce here.
  // It's ephemeral (in-memory, gone on reload) and overwritten on the next request;
  // we clear it explicitly on verify / change-phone below.
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
            onVerified={() => {
              clear();
              void navigate("/", { replace: true });
            }}
            onChangePhone={() => {
              clear();
              void navigate("/login", { replace: true });
            }}
          />
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
