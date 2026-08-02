import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { OtpForm } from "@/features/auth-by-otp";
import { AuthLayout } from "@/pages/login/AuthLayout";
import { useAuthFlowStore } from "@/pages/login";
import { isSafeReturnPath } from "@/shared/config";
import { Card, CardBody } from "@/shared/ui";

/** OTP code entry screen — step 2 of the login flow. */
export function OtpPage() {
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const returnTo = from && isSafeReturnPath(from) ? from : "/cabinet";
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
    return <Navigate to="/cabinet/login" replace />;
  }

  return (
    // The subtitle was `auth.loginSubtitle` — «Введите номер телефона…» on the
    // screen that asks for the CODE. `auth.codeSubtitle` names the phone, and
    // OtpForm already renders it inside the card, so the page-level line is
    // dropped rather than duplicated.
    <AuthLayout title={t("auth.codeTitle")}>
      <Card>
        <CardBody>
          <OtpForm
            phone={phone}
            initialCooldown={cooldownSeconds}
            onVerified={() => {
              clear();
              // Honour the page the guard bounced them off, falling back to the
              // cabinet home. `RequireAuth` has always written `state.from`;
              // until now nothing read it, so every sign-in landed on the home
              // screen no matter which deep link brought the visitor here.
              void navigate(returnTo, { replace: true });
            }}
            onChangePhone={() => {
              clear();
              void navigate("/cabinet/login", { replace: true });
            }}
          />
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
