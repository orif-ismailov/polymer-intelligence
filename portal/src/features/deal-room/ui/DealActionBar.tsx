import { useState } from "react";

import { useTranslation } from "react-i18next";

import { dealApi } from "@/entities/deal";
import type { DealDetail, DealStatus } from "@/entities/deal";
import { Alert, Button, Textarea } from "@/shared/ui";

/**
 * Statuses that end or freeze the deal. They need a typed reason, and they sit
 * apart from the forward action so nobody cancels by muscle memory.
 */
const DESTRUCTIVE: DealStatus[] = ["cancelled", "disputed"];

interface DealActionBarProps {
  companyId: number;
  deal: DealDetail;
  onChanged: () => void;
}

/**
 * The action bar renders `deal.available_transitions` verbatim — the server's
 * state machine already knows what this side may do from this status, so the
 * rules are never restated here (and a button can never appear that the API
 * would then refuse).
 *
 * «Оплата получена» is the one action that is not a deal transition: on the
 * direct rail it marks the PAYMENT, and the deal follows (or, on postpayment,
 * stays put). It shows when the server says `can_confirm_payment`, and asks
 * first — the seller cannot take it back.
 */
export function DealActionBar({ companyId, deal, onChanged }: DealActionBarProps) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<DealStatus | null>(null);
  const [confirmingPayment, setConfirmingPayment] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forward = deal.available_transitions.filter((s) => !DESTRUCTIVE.includes(s));
  const destructive = deal.available_transitions.filter((s) => DESTRUCTIVE.includes(s));

  if (deal.available_transitions.length === 0 && !deal.can_confirm_payment) return null;

  async function act(call: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await call();
      setPending(null);
      setConfirmingPayment(false);
      setReason("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  const run = (to: DealStatus, why?: string) =>
    act(() => dealApi.transition(companyId, deal.id, to, why));
  const confirmPayment = () => act(() => dealApi.confirmPayment(companyId, deal.id));

  return (
    <div className="space-y-3">
      {error ? <Alert tone="danger" title={error} /> : null}

      {confirmingPayment ? (
        <div className="space-y-2 rounded-md border border-border bg-surface-inset p-3">
          <p className="text-sm font-medium text-text">
            {t("deals.actions.confirm.confirmPayment")}
          </p>
          <div className="flex gap-2">
            <Button loading={busy} onClick={() => void confirmPayment()}>
              {t("deals.actions.confirmPayment")}
            </Button>
            <Button variant="ghost" onClick={() => setConfirmingPayment(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : pending ? (
        <div className="space-y-2 rounded-md border border-border bg-surface-inset p-3">
          <p className="text-sm font-medium text-text">
            {t(`deals.actions.confirm.${pending}`)}
          </p>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("deals.actions.reasonPlaceholder")}
            aria-label={t("deals.actions.reasonPlaceholder")}
            rows={2}
          />
          <div className="flex gap-2">
            <Button
              variant="danger"
              loading={busy}
              disabled={!reason.trim()}
              onClick={() => void run(pending, reason.trim())}
            >
              {t("common.confirm")}
            </Button>
            <Button variant="ghost" onClick={() => setPending(null)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {deal.can_confirm_payment ? (
            <Button onClick={() => setConfirmingPayment(true)}>
              {t("deals.actions.confirmPayment")}
            </Button>
          ) : null}
          {forward.map((to) => (
            <Button key={to} loading={busy} onClick={() => void run(to)}>
              {t(`deals.actions.${to}`)}
            </Button>
          ))}
          {destructive.map((to) => (
            <Button key={to} variant="ghost" onClick={() => setPending(to)}>
              {t(`deals.actions.${to}`)}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
