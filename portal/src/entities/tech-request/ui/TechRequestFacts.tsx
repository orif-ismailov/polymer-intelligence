import { useTranslation } from "react-i18next";

import { formatDate } from "@/shared/lib";
import { SpecItem, SpecList } from "@/shared/ui";

import type { TechFeedItem, TechRequest } from "../model/types";

/**
 * The structured brief — the same facts whichever side reads them, so one
 * component serves the factory's page and the expert's.
 */
export function TechRequestFacts({ request }: { request: TechRequest | TechFeedItem }) {
  const { t } = useTranslation();
  const place = [request.city, request.country].filter(Boolean).join(", ");
  const urgency =
    request.urgency === "date" && request.needed_by
      ? formatDate(request.needed_by)
      : t(`technologists.urgency.${request.urgency}`);

  return (
    <div className="space-y-4">
      <p className="whitespace-pre-line text-sm text-text">{request.problem}</p>
      <SpecList>
        <SpecItem label={t("techRequest.form.needType")} value={t(`technologists.need.${request.need_type}`)} />
        <SpecItem label={t("techRequest.form.process")} value={t(`technologists.process.${request.process}`)} />
        <SpecItem
          label={t("techRequest.form.equipment")}
          value={[request.equipment, request.equipment_model].filter(Boolean).join(" · ")}
        />
        <SpecItem label={t("techRequest.form.product")} value={request.product} />
        {request.current_material ? (
          <SpecItem label={t("techRequest.form.currentMaterial")} value={request.current_material} />
        ) : null}
        {request.target_material ? (
          <SpecItem label={t("techRequest.form.targetMaterial")} value={request.target_material} />
        ) : null}
        {request.capacity ? (
          <SpecItem
            label={t("techRequest.form.capacity")}
            value={`${Number(request.capacity)} ${t(`technologists.capacityUnit.${request.capacity_unit ?? "kg_h"}`)}`}
            numeric
          />
        ) : null}
        <SpecItem label={t("techRequest.form.location")} value={place} />
        <SpecItem label={t("techRequest.form.urgency")} value={urgency} />
        <SpecItem label={t("techRequest.form.workFormat")} value={t(`technologists.format.${request.work_format}`)} />
        {request.languages.length > 0 ? (
          <SpecItem
            label={t("techRequest.form.languages")}
            value={request.languages.map((l) => t(`technologists.language.${l}`)).join(", ")}
          />
        ) : null}
        {request.budget_note ? (
          <SpecItem label={t("techRequest.form.budget")} value={request.budget_note} />
        ) : null}
      </SpecList>
    </div>
  );
}
