import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { BrandLogo, ShieldIcon } from "@/shared/ui";

import { LanguageMenu } from "./LanguageMenu";

interface AuthLayoutProps {
  title: string;
  /** Optional: the OTP screen states its context inside the card instead. */
  subtitle?: string;
  children: ReactNode;
}

/**
 * Shared shell for the login + OTP screens, following the mockups' entry screen
 * (sheet …39): the lockup centred over a hero heading, then the form, then the
 * "safe and reliable" reassurance — the sheet puts that promise on the screen
 * where a stranger is deciding whether to hand over their phone number.
 */
export function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <header className="flex items-center justify-end px-4 py-4">
        <LanguageMenu />
      </header>

      <main className="flex flex-1 justify-center px-4 pb-16">
        <div className="w-full max-w-md space-y-6">
          <div className="flex flex-col items-center text-center">
            {/* Also the way back to the marketplace for someone who opened the
                login by accident — this screen has no other exit. */}
            <Link to="/" aria-label={t("common.appName")}>
              <BrandLogo withTagline />
            </Link>
            <h1 className="mt-6 text-2xl font-semibold leading-tight text-text sm:text-3xl">
              {title}
            </h1>
            {subtitle ? <p className="mt-2 text-sm text-text-muted">{subtitle}</p> : null}
          </div>

          {children}

          <div className="flex items-start gap-3 rounded-lg border border-border bg-surface px-4 py-3">
            <span className="mt-0.5 shrink-0 text-brand">
              <ShieldIcon size={20} />
            </span>
            <div>
              <p className="text-sm font-medium text-text">{t("auth.trustTitle")}</p>
              <p className="mt-0.5 text-xs text-text-muted">{t("auth.trustBody")}</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
