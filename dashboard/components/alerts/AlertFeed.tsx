"use client";

/**
 * AlertFeed — table of triggered alerts from GET /alerts.
 *
 * Columns: message, severity chip (info=blue/warning=amber/critical=red),
 *          source, triggered-at (Asia/Tashkent), rule name.
 * Empty state: Bell icon + "No alerts triggered yet" / "Configure a rule to start receiving alerts."
 *
 * No hardcoded hex — all colors via Tailwind token classes.
 * Severity chip: text-status-new (blue) / text-urgency-medium (amber) / text-urgency-high (red)
 */

import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface AlertOut {
  id: number;
  kind: string;
  rule_id: number | null;
  severity: string;
  title: string;
  body: string;
  signal_id: number | null;
  request_id: number | null;
  dedupe_key: string | null;
  created_at: string;
}

// ─── Severity chip ─────────────────────────────────────────────────────────────

// Severity colors: info=blue(status-new), warning=amber(urgency-medium), critical=red(urgency-high)
const SEVERITY_CLASSES: Record<string, string> = {
  info: "text-status-new border-status-new",
  warning: "text-urgency-medium border-urgency-medium",
  critical: "text-urgency-high border-urgency-high",
};

const SEVERITY_LABELS: Record<string, string> = {
  info: "Info",
  warning: "Warning",
  critical: "Critical",
};

function SeverityChip({ severity }: { severity: string }) {
  const cls = SEVERITY_CLASSES[severity] ?? "text-foreground-muted border-foreground-muted";
  const label = SEVERITY_LABELS[severity] ?? severity;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}
    >
      {label}
    </span>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AlertFeed() {
  const { data: alerts = [], isLoading, error } = useQuery<AlertOut[]>({
    queryKey: ["alerts"],
    queryFn: () => apiFetch<AlertOut[]>("/alerts"),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 rounded-lg bg-background-tertiary animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4 text-sm text-urgency-high">
        Failed to load alerts. Please refresh.
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
        <Bell size={32} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold text-foreground">No alerts triggered yet</p>
          <p className="text-sm text-foreground-muted mt-0.5">
            Configure a rule to start receiving alerts.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-background-tertiary">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">Severity</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">Message</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">Rule</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider">Triggered At</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {alerts.map((alert) => (
            <tr key={alert.id} className="bg-background-secondary hover:bg-background-tertiary transition-colors">
              <td className="px-4 py-3 whitespace-nowrap">
                <SeverityChip severity={alert.severity} />
              </td>
              <td className="px-4 py-3">
                <div className="font-medium text-foreground">{alert.title}</div>
                {alert.body && (
                  <div className="text-xs text-foreground-muted mt-0.5 line-clamp-2">{alert.body}</div>
                )}
              </td>
              <td className="px-4 py-3 text-foreground-muted text-xs">
                {alert.rule_id !== null ? (
                  <span className="font-mono">Rule #{alert.rule_id}</span>
                ) : (
                  <span className="text-foreground-subtle">—</span>
                )}
              </td>
              <td className="px-4 py-3 whitespace-nowrap text-foreground-muted">
                <time dateTime={alert.created_at} title={alert.created_at}>
                  {formatTashkent(alert.created_at)}
                </time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
