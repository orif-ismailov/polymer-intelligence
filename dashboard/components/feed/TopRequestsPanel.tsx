"use client";

/**
 * TopRequestsPanel — compact "Top Buyer Requests" list for the Dashboard home.
 *
 * Data comes from the dashboard summary (fetched ONCE on the page) and is passed
 * in as a prop. Rows deep-link to /requests?id={id} (the master-detail link the
 * requests page already uses). Shows number, product, grade, volume,
 * target price + currency, urgency, status.
 *
 * No hardcoded hex — token classes only.
 */

import { Inbox } from "lucide-react";
import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { UrgencyChip } from "@/components/shared/UrgencyChip";
import { StatusChip } from "@/components/shared/StatusChip";
import type { DashboardTopRequest } from "@/hooks/useDashboardSummary";

interface TopRequestsPanelProps {
  requests?: DashboardTopRequest[];
  isLoading?: boolean;
}

export function TopRequestsPanel({ requests, isLoading = false }: TopRequestsPanelProps) {
  const t = useTranslations("home");
  return (
    <div className="rounded-lg bg-background-secondary border border-border">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 className="text-base font-semibold text-foreground">{t("topBuyerRequests")}</h2>
        <Link
          href="/requests"
          className="text-sm text-accent hover:text-accent-light transition-colors"
        >
          {t("viewAll")}
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <span className="ms-3 text-sm text-foreground-muted">{t("loading")}</span>
        </div>
      ) : !requests?.length ? (
        <div className="flex flex-col items-center justify-center gap-2 py-10">
          <Inbox size={28} className="text-foreground-muted" aria-hidden="true" />
          <p className="text-sm text-foreground-muted">{t("noRequests")}</p>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {requests.map((req) => (
            <li key={req.id}>
              <a
                href={`/requests?id=${req.id}`}
                className="flex items-center gap-4 px-6 py-3 hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-inset"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-foreground">
                    {req.product ?? "—"}
                    {req.grade_text ? (
                      <span className="font-normal text-foreground-muted">
                        {" · "}
                        {req.grade_text}
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-foreground-muted">{req.number}</p>
                </div>
                <span className="hidden whitespace-nowrap text-sm font-mono text-foreground sm:block">
                  {req.volume != null ? t("volumeMt", { volume: req.volume }) : "—"}
                </span>
                <span className="hidden whitespace-nowrap text-sm font-mono text-foreground md:block">
                  {req.target_price != null
                    ? t("pricePerMt", {
                        price: req.target_price,
                        currency: req.currency ?? "USD",
                      })
                    : "—"}
                </span>
                {req.urgency ? (
                  <UrgencyChip urgency={req.urgency} />
                ) : (
                  <span className="text-sm text-foreground-subtle">—</span>
                )}
                <StatusChip status={req.status} />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
