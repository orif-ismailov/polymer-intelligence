import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { useVerificationCase } from "@/entities/verification";
import type { CaseCheck } from "@/entities/verification";
import {
  Alert,
  Button,
  Card,
  CardBody,
  ChecklistRow,
  SuccessMark,
} from "@/shared/ui";
import type { ChecklistState } from "@/shared/ui";

import { CHECK_ORDER, isManufacturerType } from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import { useSubmitWizard } from "../model/useSubmitWizard";
import { CheckGlyph } from "./wizardGlyphs";

/** Backend `check_status` → the row treatment it gets. */
const CHECK_STATE: Record<string, ChecklistState> = {
  pending: "pending",
  running: "running",
  passed: "passed",
  waived: "passed",
  warning: "warning",
  unavailable: "warning",
  failed: "failed",
};

/** Poll cadence while the case still has checks in flight. */
const POLL_MS = 3000;

interface StepReviewProps {
  onBack: () => void;
  onComplete: (companyId: number) => void;
}

/**
 * Final wizard step.
 *
 * Default types: entering this screen IS the submit (register.jpeg).
 * Manufacturer: an «Almost ready» confirm sheet (companys_list.jpeg) gates the
 * submit behind an explicit «Отправить на модерацию» click.
 */
export function StepReview({ onBack, onComplete }: StepReviewProps) {
  const { t } = useTranslation();
  const accountType = useWizardDraft((s) => s.accountType);
  const manufacturer = isManufacturerType(accountType);
  const { submit, error, isSubmitting, reset } = useSubmitWizard();
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState(!manufacturer);
  const startedRef = useRef(false);

  function runSubmit(): void {
    void submit().then((id) => {
      if (id != null) setCompanyId(id);
    });
  }

  useEffect(() => {
    if (!confirmed) return;
    if (startedRef.current) return;
    startedRef.current = true;
    runSubmit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmed]);

  function handleRetry(): void {
    reset();
    runSubmit();
  }

  const checks = useVerificationCase(companyId, { refetchInterval: POLL_MS });
  const caseOut = checks.data ?? null;

  const rows: CaseCheck[] = caseOut
    ? [...caseOut.checks].sort(
        (a, b) => indexOfCheck(a.check_type) - indexOfCheck(b.check_type),
      )
    : CHECK_ORDER.map((check_type) => ({ check_type, status: "pending", detail: null }));

  const resolved = rows.every(
    (c) => CHECK_STATE[c.status] !== "pending" && CHECK_STATE[c.status] !== "running",
  );
  const anyProblem = rows.some((c) => {
    const state = CHECK_STATE[c.status] ?? "pending";
    return state === "failed" || state === "warning";
  });
  const allPassed = caseOut != null && resolved && !anyProblem;

  function handleContinue(): void {
    if (companyId == null) return;
    onComplete(companyId);
  }

  if (manufacturer && !confirmed) {
    return (
      <div className="space-y-6" data-testid="wizard-almost-ready">
        <div className="flex flex-col items-center gap-3 pt-4 text-center">
          <SuccessMark size="lg" />
          <h2 className="text-xl font-semibold text-text">{t("wizard.almostReady.title")}</h2>
          <p className="max-w-md text-sm text-text-muted">{t("wizard.almostReady.subtitle")}</p>
        </div>

        <Card>
          <CardBody className="space-y-4">
            <h3 className="text-sm font-semibold text-text">{t("wizard.almostReady.whatsNext")}</h3>
            <ol className="space-y-3 text-sm text-text-muted">
              <li>1. {t("wizard.almostReady.steps.check")}</li>
              <li>2. {t("wizard.almostReady.steps.notify")}</li>
              <li>3. {t("wizard.almostReady.steps.buyers")}</li>
            </ol>
          </CardBody>
        </Card>

        <Alert tone="info" title={t("wizard.almostReady.privacyTitle")}>
          {t("wizard.almostReady.privacyBody")}
        </Alert>

        <div className="flex flex-col gap-3">
          <Button
            type="button"
            size="lg"
            className="w-full"
            data-testid="wizard-submit-moderation"
            onClick={() => setConfirmed(true)}
          >
            {t("wizard.almostReady.submit")}
          </Button>
          <Button type="button" variant="ghost" size="lg" className="w-full" onClick={onBack}>
            {t("wizard.almostReady.saveDraft")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text">{t("wizard.review.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("wizard.review.subtitle")}</p>
      </div>

      <Card>
        <CardBody>
          <ul className="divide-y divide-border" data-testid="wizard-checks">
            {rows.map((check) => {
              const state = CHECK_STATE[check.status] ?? "pending";
              return (
                <ChecklistRow
                  key={check.check_type}
                  icon={<CheckGlyph type={check.check_type} />}
                  title={t(`verification.checkTypes.${check.check_type}`, {
                    defaultValue: check.check_type,
                  })}
                  status={t(`wizard.review.checkState.${state}`)}
                  state={state}
                  data-testid={`wizard-check-${check.check_type}`}
                />
              );
            })}
          </ul>
        </CardBody>
      </Card>

      {error ? (
        <Alert tone="danger" title={t(error.messageKey, error.messageValues ?? {})}>
          {error.detail}
        </Alert>
      ) : null}

      {error ? null : allPassed ? (
        <Card>
          <CardBody className="flex flex-col items-center py-8 text-center">
            <SuccessMark />
            <h3 className="mt-5 text-base font-semibold text-text">{t("wizard.review.passedTitle")}</h3>
            <p className="mt-1 text-sm text-text-muted">{t("wizard.review.passedBody")}</p>
          </CardBody>
        </Card>
      ) : caseOut != null && resolved ? (
        <Alert tone="warning" title={t("wizard.review.needsAttentionTitle")}>
          {t("wizard.review.needsAttentionBody")}
        </Alert>
      ) : (
        <Alert tone="info" title={t("wizard.review.runningTitle")}>
          {t("wizard.review.runningBody")}
        </Alert>
      )}

      <div className="flex gap-3">
        <Button
          variant="ghost"
          size="lg"
          onClick={onBack}
          disabled={isSubmitting || companyId != null}
          className="min-w-24"
        >
          {t("common.back")}
        </Button>
        {error && companyId == null ? (
          <Button
            size="lg"
            className="flex-1"
            loading={isSubmitting}
            onClick={handleRetry}
            data-testid="wizard-retry"
          >
            {t("common.retry")}
          </Button>
        ) : (
          <Button
            size="lg"
            className="flex-1"
            loading={isSubmitting}
            disabled={companyId == null}
            onClick={handleContinue}
            data-testid="wizard-submit"
          >
            {t("common.next")}
          </Button>
        )}
      </div>
    </div>
  );
}

/** Mockup order first, then anything the API added that we do not know about. */
function indexOfCheck(checkType: string): number {
  const index = CHECK_ORDER.indexOf(checkType);
  return index === -1 ? CHECK_ORDER.length : index;
}
