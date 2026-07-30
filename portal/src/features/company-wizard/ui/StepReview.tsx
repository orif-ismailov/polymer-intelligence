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

import { CHECK_ORDER } from "../model/constants";
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
 * Step 5 — «Проверка компании».
 *
 * Entering this screen IS the submit: the mockup has no separate confirmation
 * sheet, and by here the user has clicked «Далее» through every step of a flow
 * titled "register a company". The run is guarded by a ref so React's double
 * mount (and a re-render mid-flight) cannot submit twice.
 */
export function StepReview({ onBack, onComplete }: StepReviewProps) {
  const { t } = useTranslation();
  const { submit, error, isSubmitting, reset } = useSubmitWizard();
  const [companyId, setCompanyId] = useState<number | null>(null);
  const startedRef = useRef(false);

  function runSubmit(): void {
    void submit().then((id) => {
      if (id != null) setCompanyId(id);
    });
  }

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    runSubmit();
    // Submit is a one-shot side effect of arriving here; `submit` is recreated
    // every render, so depending on it would re-fire the whole sequence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Retry in place. Without this the only exit from a failed submit was «Назад»,
   * because «Далее» stays disabled until there is a company id — so the screen
   * that reported the failure offered no way to act on it.
   */
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

  const resolved = rows.every((c) => CHECK_STATE[c.status] !== "pending" && CHECK_STATE[c.status] !== "running");
  const anyProblem = rows.some((c) => {
    const state = CHECK_STATE[c.status] ?? "pending";
    return state === "failed" || state === "warning";
  });
  const allPassed = caseOut != null && resolved && !anyProblem;

  function handleContinue(): void {
    if (companyId == null) return;
    // Navigate only. The draft is cleared by the done screen (`RegistrationDone`),
    // NOT here: resetting first empties the draft while this wizard is still
    // mounted, and the wizard's step guard then sees an unreachable step 5 and
    // redirects to step 1 — overriding the navigation to the done sheet.
    onComplete(companyId);
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

      {/* One state at a time. A hard failure used to render alongside the blue
          «Идёт проверка… Страницу можно не закрывать», so the screen simultaneously
          reported that the submit had failed and that it was still in progress. */}
      {error ? null : allPassed ? (
        <Card>
          <CardBody className="flex flex-col items-center py-8 text-center">
            <SuccessMark />
            <h3 className="mt-5 text-base font-semibold text-text">{t("wizard.review.passedTitle")}</h3>
            <p className="mt-1 text-sm text-text-muted">{t("wizard.review.passedBody")}</p>
          </CardBody>
        </Card>
      ) : caseOut != null && resolved ? (
        // Resolved but not clean: the case is in, staff will come back on the
        // flagged points. Saying "verified" here would be a promise we cannot keep.
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
