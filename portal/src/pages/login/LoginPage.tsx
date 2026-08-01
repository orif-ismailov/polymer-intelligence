import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { PhoneForm } from "@/features/auth-by-otp";
import { Card, CardBody } from "@/shared/ui";

import { useAuthFlowStore } from "./authFlowStore";
import { AuthLayout } from "./AuthLayout";

/** Phone entry screen — step 1 of the OTP login flow. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Carry `state.from` through to the OTP step. `RequireAuth` writes it on the
  // way in; without this hop the code screen never sees it and every sign-in
  // lands on the cabinet home instead of the page the visitor asked for.
  const returnState = useLocation().state as { from?: string } | null;
  const setPending = useAuthFlowStore((s) => s.setPending);

  return (
    <AuthLayout title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")}>
      <Card>
        <CardBody>
          <PhoneForm
            onSent={(phone, cooldown) => {
              setPending(phone, cooldown);
              void navigate("/cabinet/login/code", { state: returnState });
            }}
          />
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
