import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useFactoryRfq } from "@/entities/manufacturer";
import { formatDateTime } from "@/shared/lib";
import {
  Button,
  Card,
  CardBody,
  Confetti,
  ErrorView,
  LoadingView,
  SuccessMark,
} from "@/shared/ui";

interface FactoryRfqDoneProps {
  companyId: number;
  rfqId: number;
}

/** `/cabinet/manufacturers/rfqs/:rfqId/done` — the closing sheet of the factory RFQ flow. */
export function FactoryRfqDone({ companyId, rfqId }: FactoryRfqDoneProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const query = useFactoryRfq(rfqId, companyId);

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

  const rfq = query.data;

  return (
    <div className="relative" data-testid="factory-rfq-done">
      <Confetti className="-top-6 h-64" />

      <div className="relative flex flex-col items-center pt-4 text-center">
        <SuccessMark size="lg" />
        <h1 className="mt-6 text-3xl font-semibold leading-tight text-text">
          {t("factoryRfq.done.title")}
        </h1>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-text-muted">
          {t("factoryRfq.done.body")}
        </p>
      </div>

      <Card className="mt-8">
        <CardBody className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-text-muted">{t("factoryRfq.done.numberLabel")}</p>
            <p className="num text-base font-semibold text-text" data-testid="factory-rfq-number">
              {rfq.number}
            </p>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
            <p className="text-sm text-text-muted">{t("factoryRfq.done.dateLabel")}</p>
            <p className="num text-sm text-text">
              {formatDateTime(rfq.created_at, i18n.language)}
            </p>
          </div>
        </CardBody>
      </Card>

      <div className="mt-8 space-y-3">
        <Button
          fullWidth
          size="lg"
          onClick={() => void navigate("/manufacturers")}
          data-testid="factory-rfq-done-manufacturers"
        >
          {t("factoryRfq.done.toManufacturers")}
        </Button>
        <Button
          fullWidth
          size="lg"
          variant="outline"
          onClick={() => void navigate("/cabinet")}
          data-testid="factory-rfq-done-home"
        >
          {t("factoryRfq.done.toHome")}
        </Button>
      </div>
    </div>
  );
}
