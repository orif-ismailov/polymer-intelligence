"use client";

/**
 * Alerts page (/alerts)
 *
 * AlertFeed table (triggered alerts) + RuleBuilder (create/manage rules).
 * Write actions (Create Rule, Delete Rule) hidden for non-admin roles.
 * No hardcoded hex.
 */

import { Suspense } from "react";
import { Bell } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { AlertFeed } from "@/components/alerts/AlertFeed";
import { RuleBuilder } from "@/components/alerts/RuleBuilder";

function AlertsPageContent() {
  const { role } = useAuth();
  const isAdmin = role === "admin";

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Bell size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">Alerts</h1>
          <p className="text-sm text-foreground-muted mt-0.5">
            Triggered alerts and delivery rules
          </p>
        </div>
      </div>

      {/* Alert feed */}
      <section>
        <h2 className="text-base font-semibold text-foreground mb-3">Recent Alerts</h2>
        <AlertFeed />
      </section>

      {/* Rule builder */}
      <section>
        <RuleBuilder isAdmin={isAdmin} />
      </section>
    </div>
  );
}

export default function AlertsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4 p-6">
          <div className="h-8 w-32 rounded bg-background-tertiary animate-pulse" />
          <div className="h-32 rounded bg-background-tertiary animate-pulse" />
          <div className="h-48 rounded bg-background-tertiary animate-pulse" />
        </div>
      }
    >
      <AlertsPageContent />
    </Suspense>
  );
}
