import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { PhoneForm } from "@/features/auth-by-otp";
import { Card, CardBody } from "@/shared/ui";

import { useAuthFlowStore } from "./authFlowStore";
import { AuthLayout } from "./AuthLayout";

/** Phone entry screen — step 1 of the OTP login flow. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setPending = useAuthFlowStore((s) => s.setPending);

  return (
    <AuthLayout title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")}>
      <Card>
        <CardBody>
          <PhoneForm
            onSent={(phone, cooldown) => {
              setPending(phone, cooldown);
              void navigate("/login/code");
            }}
          />
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
