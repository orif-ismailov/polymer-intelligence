import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useRequest } from "@/entities/request";
import {
  BellIcon,
  Button,
  Card,
  CardBody,
  CheckIcon,
  Confetti,
  CopyIcon,
  ErrorView,
  GitCompareIcon,
  LoadingView,
  SuccessMark,
  UsersIcon,
} from "@/shared/ui";

interface PublishDoneProps {
  companyId: number;
  requestId: number;
}

/**
 * «Заявка опубликована!» — the closing sheet after Publish.
 *
 * The public id is the request's own `number` when the API returned one, falling
 * back to a padded `#IMX-…` so the copy button still has something to hold.
 */
export function PublishDone({ companyId, requestId }: PublishDoneProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const query = useRequest(requestId, companyId);
  const [copied, setCopied] = useState(false);

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

  const request = query.data;
  const publicId = request.number?.startsWith("#")
    ? request.number
    : request.number
      ? `#${request.number}`
      : `#IMX-${String(request.id).padStart(6, "0")}`;

  function copy(): void {
    void navigator.clipboard?.writeText(publicId).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  }

  const nextSteps = [
    { icon: <UsersIcon size={18} />, key: "offers" as const },
    { icon: <BellIcon size={18} />, key: "notify" as const },
    { icon: <GitCompareIcon size={18} />, key: "compare" as const },
  ];

  return (
    <div className="relative" data-testid="request-wizard-done">
      <div className="mb-4">
        <button
          type="button"
          onClick={() => void navigate("/requests")}
          className="text-sm font-medium text-brand hover:underline"
          data-testid="request-wizard-done-close"
        >
          {t("common.close")}
        </button>
      </div>

      <Confetti className="-top-6 h-64" />

      <div className="relative flex flex-col items-center pt-4 text-center">
        <SuccessMark size="lg" />
        <h1 className="mt-6 text-3xl font-semibold leading-tight text-text">
          {t("requestWizard.done.title")}
        </h1>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-text-muted">
          {t("requestWizard.done.body")}
        </p>
      </div>

      <Card className="mt-8">
        <CardBody>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-text-muted">{t("requestWizard.done.idLabel")}</p>
              <p
                className="num mt-1 text-xl font-semibold text-text"
                data-testid="request-wizard-public-id"
              >
                {publicId}
              </p>
            </div>
            <button
              type="button"
              onClick={copy}
              aria-label={t("requestWizard.done.copyId")}
              className="rounded-md border border-border p-2.5 text-text-muted transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {copied ? <CheckIcon size={18} /> : <CopyIcon size={18} />}
            </button>
          </div>
        </CardBody>
      </Card>

      <div className="mt-8">
        <h2 className="mb-3 text-base font-semibold text-text">
          {t("requestWizard.done.nextTitle")}
        </h2>
        <ul className="divide-y divide-border overflow-hidden rounded-md border border-border bg-surface">
          {nextSteps.map((step) => (
            <li key={step.key} className="flex items-start gap-3 px-4 py-3.5">
              <span className="mt-0.5 shrink-0 text-brand">{step.icon}</span>
              <span className="text-sm leading-relaxed text-text">
                {t(`requestWizard.done.next.${step.key}`)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-6 space-y-3">
        <Button
          fullWidth
          size="lg"
          onClick={() => void navigate("/requests")}
          data-testid="request-wizard-done-list"
        >
          {t("requestWizard.done.toRequests")}
        </Button>
        <Button
          fullWidth
          size="lg"
          variant="outline"
          onClick={() => void navigate("/requests/new/1")}
          data-testid="request-wizard-done-another"
        >
          {t("requestWizard.done.createAnother")}
        </Button>
      </div>
    </div>
  );
}
