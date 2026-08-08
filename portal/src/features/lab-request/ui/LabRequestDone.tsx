import { useTranslation } from "react-i18next";

import type { LabRequest } from "@/entities/lab-request";
import { Confetti, LinkButton, SuccessMark } from "@/shared/ui";

import { LabRequestSummary } from "./LabRequestSummary";

interface LabRequestDoneProps {
  request: LabRequest;
}

/** «Заявка отправлена» — the success chrome around the shared summary. */
export function LabRequestDone({ request }: LabRequestDoneProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-6" data-testid="lab-request-done">
      <Confetti />

      <div className="flex flex-col items-center gap-3 text-center">
        <SuccessMark size="lg" />
        <h1 className="text-xl font-semibold text-text">{t("labRequest.doneTitle")}</h1>
        <p className="max-w-md text-sm leading-relaxed text-text-muted">
          {t("labRequest.doneBody")}
        </p>
      </div>

      <LabRequestSummary request={request} />

      <div className="flex flex-col gap-2 sm:flex-row">
        <LinkButton variant="outline" fullWidth to="/cabinet/lab">
          {t("labRequest.myRequests")}
        </LinkButton>
        <LinkButton fullWidth to="/laboratories">
          {t("labRequest.backToDirectory")}
        </LinkButton>
      </div>
    </div>
  );
}
