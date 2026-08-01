import { useEffect } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { useCompany } from "@/entities/company";
import { coerceLang } from "@/shared/i18n";
import { formatDateShort } from "@/shared/lib";
import {
  Button,
  Card,
  CardBody,
  Confetti,
  ErrorView,
  LoadingView,
  ShieldCheckIcon,
  SpecItem,
  SpecList,
  SuccessMark,
} from "@/shared/ui";

import { useWizardDraft } from "../model/draftStore";

interface RegistrationDoneProps {
  companyId: number;
}

/**
 * «Регистрация завершена!» — the closing sheet.
 *
 * The status line is the company's *actual* state, not the mockup's literal
 * "Verified Company": a freshly submitted company is `pending_verification` until
 * staff close the case, and printing a trust badge it has not earned is the one
 * thing this screen must not do.
 */
export function RegistrationDone({ companyId }: RegistrationDoneProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const query = useCompany(companyId);
  const resetDraft = useWizardDraft((s) => s.reset);

  /**
   * The registration is over, so the (persisted) draft is cleared here rather than
   * in StepReview. Clearing it while the wizard was still mounted made its step
   * guard treat step 5 as unreachable and bounce the user back to step 1 instead of
   * showing this sheet.
   */
  useEffect(() => {
    resetDraft();
  }, [resetDraft]);

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;

  if (query.isError || !query.data) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const company = query.data;
  const verified = company.status === "verified";
  const role = company.roles[0]?.role;

  return (
    <div className="relative" data-testid="wizard-done">
      <Confetti className="-top-6 h-64 " />

      <div className="relative flex flex-col items-center pt-6 text-center">
        <SuccessMark size="lg" />
        <h1 className="mt-6 text-3xl font-semibold leading-tight text-text">
          {t("wizard.done.title")}
        </h1>
        <p className="mt-3 text-sm text-text-muted">
          {t("wizard.done.subtitle")}{" "}
          <span className="font-medium text-text">
            IMEX <span className="text-brand">AI</span>
          </span>
        </p>
      </div>

      <Card className="mt-8">
        <CardBody className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-text-muted">
                {t("wizard.done.statusLabel")}
              </p>
              <p
                className={`mt-1 text-xl font-semibold ${verified ? "text-brand" : "text-text"}`}
                data-testid="wizard-done-status"
              >
                {verified
                  ? t("wizard.done.verified")
                  : t(`companyStatus.${company.status}`)}
              </p>
            </div>
            <span className={verified ? "text-brand" : "text-text-subtle"}>
              <ShieldCheckIcon size={28} />
            </span>
          </div>

          <SpecList variant="justified" columns={1}>
            <SpecItem
              label={t("wizard.done.companyId")}
              value={company.public_id}
            />
            <SpecItem
              label={t("wizard.done.registeredAt")}
              value={formatDateShort(company.registration_date, lang)}
              numeric
            />
            <SpecItem
              label={t("wizard.done.checkStatus")}
              value={t(
                `caseStatus.${company.case?.status ?? company.active_case?.status ?? "draft"}`,
              )}
            />
            <SpecItem
              label={t("wizard.done.accessLevel")}
              value={
                role ? t(`businessRole.${role}`) : t("common.notSpecified")
              }
            />
          </SpecList>
        </CardBody>
      </Card>

      <div className="mt-6 space-y-3">
        <Button
          fullWidth
          size="lg"
          onClick={() => void navigate("/cabinet")}
          data-testid="wizard-done-cabinet"
        >
          {t("wizard.done.toCabinet")}
        </Button>
        <button
          type="button"
          onClick={() => void navigate("/cabinet/offers/new")}
          className="w-full rounded-sm py-2 text-sm font-medium text-text transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {t("wizard.done.toPublish")}
        </button>
      </div>
    </div>
  );
}
