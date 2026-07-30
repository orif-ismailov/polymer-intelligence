import { useState } from "react";

import { useTranslation } from "react-i18next";

import {
  useTransitionSample,
  type SampleRequest,
  type SampleRequestStatus,
} from "@/entities/sample";
import { Alert, Button, FormField, Input } from "@/shared/ui";

interface SampleActionsProps {
  sample: SampleRequest;
  companyId: number;
}

/** Moves that need something typed before they can be made. */
const NEEDS_REASON: SampleRequestStatus[] = ["declined", "rejected_by_buyer"];
const NEEDS_SHIPMENT: SampleRequestStatus[] = ["sent"];

/**
 * The buttons for whichever side is looking.
 *
 * Built from `available_transitions`, which the server computes from its own
 * table — the UI does not re-derive who may do what. A second copy of the rules
 * in TypeScript would disagree with the server exactly when it mattered (and
 * would happily offer a seller the "confirm delivery" button that closes their
 * own dispute).
 */
export function SampleActions({ sample, companyId }: SampleActionsProps) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<SampleRequestStatus | null>(null);
  const [reason, setReason] = useState("");
  const [courier, setCourier] = useState("");
  const [tracking, setTracking] = useState("");
  const transition = useTransitionSample();

  if (sample.available_transitions.length === 0) return null;

  function reset(): void {
    setPending(null);
    setReason("");
    setCourier("");
    setTracking("");
  }

  function submit(to: SampleRequestStatus): void {
    transition.mutate(
      {
        sampleId: sample.id,
        company_id: companyId,
        to_status: to,
        reason: reason.trim() || null,
        courier: courier.trim() || null,
        tracking_ref: tracking.trim() || null,
      },
      { onSuccess: reset },
    );
  }

  function press(to: SampleRequestStatus): void {
    // A move that needs a reason or a tracking number opens its form first —
    // the API would refuse it, and being refused is a worse way to find out.
    if (NEEDS_REASON.includes(to) || NEEDS_SHIPMENT.includes(to)) {
      setPending(to);
      return;
    }
    submit(to);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {sample.available_transitions.map((to) => (
          <Button
            key={to}
            size="sm"
            variant={NEEDS_REASON.includes(to) ? "ghost" : "secondary"}
            disabled={transition.isPending}
            onClick={() => press(to)}
          >
            {t(`samples.action.${to}`)}
          </Button>
        ))}
      </div>

      {pending && NEEDS_REASON.includes(pending) ? (
        <div className="space-y-3 rounded-lg border border-border bg-surface-inset p-3">
          <FormField label={t("samples.reason")} required>
            {({ id }) => (
              <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />
            )}
          </FormField>
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={transition.isPending}
              disabled={reason.trim() === ""}
              onClick={() => submit(pending)}
            >
              {t("common.confirm")}
            </Button>
            <Button size="sm" variant="ghost" onClick={reset}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : null}

      {pending && NEEDS_SHIPMENT.includes(pending) ? (
        <div className="space-y-3 rounded-lg border border-border bg-surface-inset p-3">
          <p className="text-sm text-text-muted">{t("samples.shipmentHint")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label={t("samples.courier")} required>
              {({ id }) => (
                <Input id={id} value={courier} onChange={(e) => setCourier(e.target.value)} />
              )}
            </FormField>
            <FormField label={t("samples.tracking")} required>
              {({ id }) => (
                <Input id={id} value={tracking} onChange={(e) => setTracking(e.target.value)} />
              )}
            </FormField>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              loading={transition.isPending}
              disabled={courier.trim() === "" || tracking.trim() === ""}
              onClick={() => submit(pending)}
            >
              {t("common.confirm")}
            </Button>
            <Button size="sm" variant="ghost" onClick={reset}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : null}

      {transition.error ? <Alert tone="danger">{t("errors.generic")}</Alert> : null}
    </div>
  );
}
