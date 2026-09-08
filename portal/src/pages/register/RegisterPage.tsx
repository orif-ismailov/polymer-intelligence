import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { RegisterForm } from "@/features/register-account";
import { AuthLayout } from "@/pages/login";
import { Card, CardBody } from "@/shared/ui";

/**
 * Access-request screen.
 *
 * Not a sign-up: submitting creates no session and hands over no credentials. Staff
 * read the request, decide, and issue a login and password — which arrive in the
 * contract, not in this browser. The next screen says exactly that.
 */
export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <AuthLayout title={t("register.title")} subtitle={t("register.subtitle")}>
      <Card>
        <CardBody>
          <RegisterForm
            onSubmitted={() => void navigate("/cabinet/register/done", { replace: true })}
          />
        </CardBody>
      </Card>

      <p className="text-center text-sm text-text-muted">
        {t("register.haveAccount")}{" "}
        <Link to="/cabinet/login" className="font-medium text-brand hover:underline">
          {t("auth.signIn")}
        </Link>
      </p>
    </AuthLayout>
  );
}
