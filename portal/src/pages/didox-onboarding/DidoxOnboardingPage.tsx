import { useEffect } from "react";

import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { useActiveCompany } from "@/entities/company";
import { useDidoxStatus } from "@/entities/edi";
import {
  DidoxAccountStep,
  DidoxOfferStep,
  markPrompted,
} from "@/features/didox-session";
import {
  Alert,
  Card,
  CardBody,
  ErrorView,
  LinkButton,
  LoadingView,
  PageHeader,
  StatusStepper,
  SuccessMark,
} from "@/shared/ui";
import type { StatusStep } from "@/shared/ui";

/**
 * «Подключение к Didox» — where the owner of a verified company is taken on
 * entering the cabinet, until the company can send and sign through Didox.
 *
 * Two steps: an account at Didox (register, or sign in to an existing one), and
 * Didox's public offer — read here in full, then signed. «Позже» always works:
 * the cabinet stays usable, only signing contracts through Didox waits for this.
 */
export function DidoxOnboardingPage() {
  const { t } = useTranslation();
  const { activeCompany } = useActiveCompany();
  const phone = useAuthStore((s) => s.account?.phone ?? "");
  const companyId = activeCompany?.id ?? null;
  const status = useDidoxStatus(companyId);

  // Shown once per visit: leaving this screen by any route counts as «Позже».
  useEffect(() => {
    if (companyId != null) markPrompted(companyId);
  }, [companyId]);

  if (!activeCompany || status.isLoading)
    return <LoadingView label={t("common.loading")} />;
  if (!status.data) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void status.refetch()}
      />
    );
  }

  const { state, can_onboard: canOnboard } = status.data;
  if (state === "disabled") return <Navigate to="/cabinet" replace />;

  const ready = state === "ready";
  const steps: StatusStep[] = [
    {
      id: "account",
      label: t("didoxOnboarding.steps.account"),
      state: state === "not_registered" ? "current" : "done",
    },
    {
      id: "offer",
      label: t("didoxOnboarding.steps.offer"),
      state: ready
        ? "done"
        : state === "offer_unsigned"
          ? "current"
          : "pending",
    },
  ];
  const companyName =
    activeCompany.short_name ??
    activeCompany.legal_name ??
    activeCompany.tax_id;

  return (
    <div className="mx-auto max-w-3xl space-y-5" data-testid="didox-onboarding">
      <PageHeader
        title={t("didoxOnboarding.title")}
        subtitle={t("didoxOnboarding.subtitle", { company: companyName })}
        actions={
          ready ? null : (
            <LinkButton to="/cabinet" variant="ghost" data-testid="didox-later">
              {t("didoxOnboarding.later")}
            </LinkButton>
          )
        }
      />

      <Card>
        <CardBody className="space-y-3">
          <p className="text-sm text-text-muted">{t("didoxOnboarding.why")}</p>
          <StatusStepper steps={steps} />
        </CardBody>
      </Card>

      {ready ? (
        <Card data-testid="didox-onboarding-done">
          <CardBody className="flex flex-col items-center gap-3 py-8 text-center">
            <SuccessMark />
            <p className="text-base font-medium text-text">
              {t("didoxOnboarding.done.title")}
            </p>
            <p className="text-sm text-text-muted">
              {t("didoxOnboarding.done.body")}
            </p>
            <LinkButton to="/cabinet">
              {t("didoxOnboarding.done.cta")}
            </LinkButton>
          </CardBody>
        </Card>
      ) : !canOnboard ? (
        <Alert tone="info" title={t("didox.ownerOnly")} />
      ) : state === "not_registered" ? (
        <DidoxAccountStep
          companyId={activeCompany.id}
          taxId={activeCompany.tax_id}
          phone={phone}
        />
      ) : (
        <DidoxOfferStep
          companyId={activeCompany.id}
          taxId={activeCompany.tax_id}
        />
      )}
    </div>
  );
}
