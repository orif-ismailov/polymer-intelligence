import { useTranslation } from "react-i18next";

import type { LabRequest } from "@/entities/lab-request";
import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import { Card, CardBody, SpecItem, SpecList, Stepper } from "@/shared/ui";

interface LabRequestSummaryProps {
  request: LabRequest;
}

/**
 * One request, read back.
 *
 * Shared by the buyer's success sheet and their detail page: the facts are the
 * same either way, and only the chrome around them differs (confetti and CTAs
 * there, a page header here). Two copies of this list would have drifted the
 * first time a field was added.
 *
 * BUYER-side only. A laboratory reads a request through the pool, whose payload
 * is a different model on purpose — it carries no contact block.
 *
 * The three dots are the request LIFECYCLE, which is what the mockup's stepper
 * actually depicts — the form is one screen, so a stepper above it would have
 * counted to three and never moved.
 */
const LIFECYCLE = ["submitted", "in_progress", "quoted"] as const;

export function LabRequestSummary({ request }: LabRequestSummaryProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);

  // `closed`/`rejected`/`viewed` are not on the rail: it shows progress toward a
  // quote, and `indexOf` returning -1 for them correctly pins the dot at stage 1
  // rather than inventing a fourth state.
  const stageIndex = Math.max(
    0,
    LIFECYCLE.indexOf(request.status as (typeof LIFECYCLE)[number]),
  );
  const steps = LIFECYCLE.map((key, i) => ({
    id: i + 1,
    label: t(`labRequest.lifecycle.${key}`),
  }));

  return (
    <div className="space-y-5">
      <Stepper
        steps={steps}
        current={stageIndex + 1}
        // Explicit: left to itself `Stepper` assumes everything before `current`
        // is complete, which is right for a wizard someone walked through and
        // wrong for a state a request happens to be in.
        completedIds={steps.slice(0, stageIndex).map((s) => s.id)}
        variant="stacked"
      />

      <Card>
        <CardBody>
          <SpecList>
            <SpecItem label={t("labRequest.number")} value={request.number} numeric />
            <SpecItem
              label={t("labRequest.buyer")}
              value={request.buyer_name ?? "—"}
            />
            <SpecItem label={t("labRequest.product")} value={request.product_text} />
            {request.grade_text ? (
              <SpecItem label={t("labRequest.grade")} value={request.grade_text} />
            ) : null}
            {request.study_type ? (
              <SpecItem
                label={t("labRequest.studyType")}
                value={t(`labRequest.studyTypes.${request.study_type}`, {
                  defaultValue: request.study_type,
                })}
              />
            ) : null}
            <SpecItem
              label={t("labRequest.methods")}
              value={
                request.methods
                  .map((m) => t(`labRequest.methodOptions.${m}`, { defaultValue: m }))
                  .join(", ") || "—"
              }
              span={2}
            />
            {request.sample_qty ? (
              <SpecItem label={t("labRequest.sampleQty")} value={request.sample_qty} />
            ) : null}
            {request.purpose ? (
              <SpecItem
                label={t("labRequest.purpose")}
                value={t(`labRequest.purposes.${request.purpose}`, {
                  defaultValue: request.purpose,
                })}
              />
            ) : null}
            {request.desired_date ? (
              <SpecItem
                label={t("labRequest.desiredDate")}
                value={formatDate(request.desired_date, lang)}
              />
            ) : null}
            {request.is_urgent ? (
              <SpecItem label={t("labRequest.urgent")} value={t("common.yes")} />
            ) : null}
            {request.comment ? (
              <SpecItem label={t("labRequest.comment")} value={request.comment} span={2} />
            ) : null}
            {request.contact_name || request.contact_phone ? (
              <SpecItem
                label={t("labRequest.contact")}
                value={[request.contact_name, request.contact_phone]
                  .filter(Boolean)
                  .join(" · ")}
                span={2}
              />
            ) : null}
          </SpecList>
        </CardBody>
      </Card>
    </div>
  );
}
