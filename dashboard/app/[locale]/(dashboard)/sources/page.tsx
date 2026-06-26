"use client";

/**
 * Sources page (/sources)
 *
 * Lists all configured data sources with health info.
 * "Add Source" button opens the AddSourceWizard dialog.
 *
 * Empty state shown when no sources exist.
 * No hardcoded hex.
 */

import { useState, Suspense } from "react";
import { useTranslations } from "next-intl";
import { Plus, Server } from "lucide-react";
import { SourcesList } from "@/components/sources/SourcesList";
import { AddSourceWizard } from "@/components/sources/AddSourceWizard";

function SourcesPageContent() {
  const t = useTranslations("sources");
  const [wizardOpen, setWizardOpen] = useState(false);

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Server size={24} className="text-foreground-muted" aria-hidden="true" />
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
          </div>
          <p className="text-sm text-foreground-muted mt-1">
            {t("subtitle")}
          </p>
        </div>
        <button
          onClick={() => setWizardOpen(true)}
          className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
        >
          <Plus size={16} aria-hidden="true" />
          {t("addSource")}
        </button>
      </div>

      {/* Sources list */}
      <SourcesList />

      {/* Wizard dialog */}
      <AddSourceWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />
    </div>
  );
}

export default function SourcesPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4 p-6">
          <div className="h-8 w-48 rounded bg-background-tertiary animate-pulse" />
          <div className="h-14 rounded bg-background-tertiary animate-pulse" />
          <div className="h-14 rounded bg-background-tertiary animate-pulse" />
          <div className="h-14 rounded bg-background-tertiary animate-pulse" />
        </div>
      }
    >
      <SourcesPageContent />
    </Suspense>
  );
}
