import { useTranslation } from "react-i18next";

import type { LogisticsRequest } from "@/entities/logistics-request";
import { Confetti, LinkButton, SuccessMark } from "@/shared/ui";

import { LogisticsRequestSummary } from "./LogisticsRequestSummary";

interface LogisticsRequestDoneProps {
  request: LogisticsRequest;
}

/** «Заявка отправлена» — the success chrome around the shared summary. */
export function LogisticsRequestDone({ request }: LogisticsRequestDoneProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-6" data-testid="logistics-request-done">
      <Confetti />

      <div className="flex flex-col items-center gap-3 text-center">
        <SuccessMark size="lg" />
        <h1 className="text-xl font-semibold text-text">{t("logisticsRequest.doneTitle")}</h1>
        <p className="max-w-md text-sm leading-relaxed text-text-muted">
          {t("logisticsRequest.doneBody")}
        </p>
      </div>

      <LogisticsRequestSummary request={request} />

      <div className="flex flex-col gap-2 sm:flex-row">
        <LinkButton variant="outline" fullWidth to="/cabinet/logistics/requests">
          {t("logisticsRequest.myRequests")}
        </LinkButton>
        <LinkButton fullWidth to="/logistics">
          {t("logisticsRequest.backToDirectory")}
        </LinkButton>
      </div>
    </div>
  );
}
