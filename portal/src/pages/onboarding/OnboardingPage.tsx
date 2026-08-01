import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { useLogout } from "@/entities/account";
import { LanguageMenu } from "@/pages/login";
import {
  BrandLogo,
  Button,
  Card,
  CardBody,
  CloseIcon,
  FlowHeader,
  IconButton,
  ShieldIcon,
} from "@/shared/ui";

import { RegistrationHero } from "./RegistrationHero";

/**
 * «Регистрация на IMEX AI» — the gate a signed-in account with no company sees.
 *
 * The cabinet is company-scoped end to end (offers, inquiries, deals, contracts
 * all hang off an active company), so there is nothing behind this screen to let
 * someone through to. The mockup's "already have an account? sign in" line is
 * dropped: by the time this renders they are signed in, and the ✕ is the way out
 * — it logs out, which is the only thing "dismiss" can mean here.
 */
export function OnboardingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const logout = useLogout();

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col px-4 pb-10 pt-4">
        <FlowHeader
          leading={
            <IconButton
              label={t("nav.logout")}
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              data-testid="onboarding-exit"
            >
              <CloseIcon size={20} />
            </IconButton>
          }
          trailing={<LanguageMenu compact />}
          className="[&>div:last-child]:w-auto"
        />

        <div className="mt-6 flex flex-col items-center text-center">
          {/* Goes to the storefront, not to the cabinet: there is no cabinet to
              reach yet, which is the whole reason this screen exists. The ✕
              above still signs out. */}
          <Link to="/" aria-label={t("common.appName")}>
            <BrandLogo withTagline />
          </Link>
          <h1 className="mt-6 text-3xl font-semibold leading-tight text-text">
            {t("onboarding.title")}{" "}
            <span className="text-brand">
              IMEX AI
            </span>
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-text-muted">{t("onboarding.subtitle")}</p>
        </div>

        {/* `mt-auto` on the closing block: the sheet anchors its promise + CTA to
            the bottom edge, so the hero takes the slack on a tall phone instead
            of leaving a gap under the button. */}
        <RegistrationHero className="my-6" />

        <Card className="mt-auto">
          <CardBody className="flex items-start gap-3">
            <span className="mt-0.5 shrink-0 text-brand">
              <ShieldIcon size={38} />
            </span>
            <div>
              <p className="text-sm font-semibold text-text">{t("onboarding.trustTitle")}</p>
              <p className="mt-1 text-sm leading-relaxed text-text-muted">
                {t("onboarding.trustBody")}
              </p>
            </div>
          </CardBody>
        </Card>

        <Button
          fullWidth
          size="lg"
          className="mt-6"
          onClick={() => void navigate("/cabinet/companies/new/1")}
          data-testid="onboarding-start"
        >
          {t("onboarding.start")}
        </Button>
      </div>
    </div>
  );
}
