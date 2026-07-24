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
} from "@/shared/ui";

import { CheckRow } from "./CheckRow";

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
      <CardHeader className="flex items-center justify-between">
        <CardTitle>{t("verification.checks")}</CardTitle>
        <CaseStatusBadge status={caseOut.status} />
      </CardHeader>
      <CardBody className="space-y-4">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-text-muted">{t("verification.caseType")}</dt>
            <dd className="font-medium text-text">{caseOut.case_type}</dd>
          </div>
          <div>
            <dt className="text-text-muted">{t("verification.submittedAt")}</dt>
            <dd className="font-medium text-text">{formatDateTime(caseOut.submitted_at, lang)}</dd>
          </div>
        </dl>

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
