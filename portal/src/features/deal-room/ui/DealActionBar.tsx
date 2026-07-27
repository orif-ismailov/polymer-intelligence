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
 */
export function DealActionBar({ companyId, deal, onChanged }: DealActionBarProps) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<DealStatus | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forward = deal.available_transitions.filter((s) => !DESTRUCTIVE.includes(s));
  const destructive = deal.available_transitions.filter((s) => DESTRUCTIVE.includes(s));

  if (deal.available_transitions.length === 0) return null;

  async function run(to: DealStatus, why?: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await dealApi.transition(companyId, deal.id, to, why);
      setPending(null);
      setReason("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error ? <Alert tone="danger" title={error} /> : null}

      {pending ? (
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
