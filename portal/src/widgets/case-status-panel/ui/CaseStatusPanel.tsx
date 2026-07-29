import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { CaseStatusBadge, useVerificationCase } from "@/entities/verification";
import type { CaseOut } from "@/entities/verification";
import { CHECK_TO_STEP } from "@/features/company-wizard";
import { SubmitVerificationButton } from "@/features/submit-verification";
import { coerceLang } from "@/shared/i18n";
import { formatDateTime } from "@/shared/lib";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorView,
  LoadingView,
  ProgressRing,
  SpecItem,
  SpecList,
} from "@/shared/ui";

import { CheckRow } from "./CheckRow";

/**
 * A check is resolved once it has an answer of any kind — `pending` and `running`
 * are the only two states still in flight (shared/config/enums.ts). Everything
 * else, including `unavailable` and `waived`, is a check that has finished
 * telling us something.
 */
const RESOLVED_CHECKS = new Set(["passed", "warning", "failed", "unavailable", "waived"]);

function completionPercent(checks: CaseOut["checks"]): number {
  if (checks.length === 0) return 0;
  const done = checks.filter((c) => RESOLVED_CHECKS.has(c.status)).length;
  return Math.round((done / checks.length) * 100);
}

interface CaseStatusPanelProps {
  companyId: number;
  /** Fallback case from the company detail payload, used before the case query resolves. */
  fallbackCase?: CaseOut | null;
}

/** Which wizard step to deep-link to when the case needs more information. */
function firstActionableStep(caseOut: CaseOut): number {
  const failing = caseOut.checks.find(
    (c) => c.status === "failed" || c.status === "warning",
  );
  if (failing) return CHECK_TO_STEP[failing.check_type] ?? 1;
  return 1;
}

/**
 * Verification case widget: per-check chips with explanations, a needs_info
 * banner that deep-links back into the wizard, and submit / resubmit actions.
 */
export function CaseStatusPanel({ companyId, fallbackCase }: CaseStatusPanelProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const query = useVerificationCase(companyId);

  const caseOut = query.data ?? fallbackCase ?? null;

  if (query.isLoading && !fallbackCase) {
    return <LoadingView label={t("common.loading")} />;
  }

  // A 404 here just means "no case yet" — offer to submit.
  if (!caseOut) {
    return (
      <EmptyState
        title={t("verification.noCase")}
        description={t("verification.noCaseBody")}
        action={<SubmitVerificationButton companyId={companyId} onSubmitted={() => void query.refetch()} />}
      />
    );
  }

  if (query.isError && !fallbackCase) {
    return (
      <ErrorView
        title={t("errors.loadFailed")}
        retryLabel={t("common.retry")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const needsInfo = caseOut.status === "needs_info";
  const canResubmit = caseOut.status === "needs_info" || caseOut.status === "rejected";

  return (
    <Card>
      <CardHeader action={<CaseStatusBadge status={caseOut.status} />}>
        <CardTitle>{t("verification.checks")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {/* The mockups lead this screen with the dial, not with the metadata:
            "how far along am I" is the question a client opens it to answer. */}
        {caseOut.checks.length > 0 ? (
          <div className="flex justify-center py-2">
            <ProgressRing
              value={completionPercent(caseOut.checks)}
              ariaLabel={t("verification.checks")}
            />
          </div>
        ) : null}

        <SpecList>
          <SpecItem label={t("verification.caseType")} value={caseOut.case_type} />
          <SpecItem
            label={t("verification.submittedAt")}
            value={formatDateTime(caseOut.submitted_at, lang)}
            numeric
          />
        </SpecList>

        {needsInfo ? (
          <Alert
            tone="warning"
            title={t("verification.needsInfoTitle")}
            action={
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate(`/companies/new/${firstActionableStep(caseOut)}`)}
              >
                {t("verification.fixStep")}
              </Button>
            }
          >
            {t("verification.needsInfoBody")}
          </Alert>
        ) : null}

        {caseOut.checks.length > 0 ? (
          <ul className="divide-y divide-border">
            {caseOut.checks.map((check) => (
              <CheckRow key={`${check.check_type}-${check.status}`} check={check} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">{t("verification.checkDetail.empty")}</p>
        )}

        {canResubmit ? (
          <div className="border-t border-border pt-4">
            <SubmitVerificationButton
              companyId={companyId}
              resubmit
              onSubmitted={() => void query.refetch()}
            />
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
