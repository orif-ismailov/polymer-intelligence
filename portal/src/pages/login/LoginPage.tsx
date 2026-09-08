import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { LoginForm } from "@/features/auth-by-password";
import { Card, CardBody } from "@/shared/ui";

import { AuthLayout } from "./AuthLayout";

/**
 * Sign-in screen: the login and password staff issued.
 *
 * There is no `state.from` handling here any more. The form writes the session and
 * `RedirectIfAuthed` — which wraps this route — reads `state.from` and navigates the
 * instant a token appears. That guard used to be racing a two-screen OTP flow that
 * had to carry the return path itself; with one screen it is simply the only mover.
 */
export function LoginPage() {
  const { t } = useTranslation();

  return (
    <AuthLayout title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")}>
      <Card>
        <CardBody>
          <LoginForm />
        </CardBody>
      </Card>

      <p className="text-center text-sm text-text-muted">
        {t("auth.noAccount")}{" "}
        <Link to="/cabinet/register" className="font-medium text-brand hover:underline">
          {t("auth.registerCta")}
        </Link>
      </p>
    </AuthLayout>
  );
}
