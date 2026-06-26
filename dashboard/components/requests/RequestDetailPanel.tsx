"use client";

/**
 * RequestDetailPanel — 400px right Sheet for Purchase Request detail.
 *
 * Phase 4, Plan 05, Task 3: Full implementation.
 * This file is created here as a shell so Task 2 (page.tsx) can import it;
 * the full implementation is filled in by Task 3.
 *
 * Opens when ?id= URL param is set.
 * Uses shadcn Sheet side="right", role="dialog", aria-labelledby.
 * Width fixed at 400px.
 *
 * Sections: Request Details / Source Information / AI Analysis / Files / Actions.
 * UI-SPEC §Right detail panel.
 * No hardcoded hex — token classes only.
 */

import { useCallback } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { StatusChip } from "@/components/shared/StatusChip";
import { UrgencyChip } from "@/components/shared/UrgencyChip";
import { AiAnalysisBlock } from "@/components/requests/AiAnalysisBlock";
import { RequestActions } from "@/components/requests/RequestActions";
import {
  Sheet,
  SheetContent,
} from "@/components/ui/sheet";

/** RequestDetailOut from app.schemas.dashboard (04-04). */
export interface RequestDetail {
  id: number;
  number: string;
  status: string;
  product_id: number;
  grade_text: string | null;
  polymer_type: string | null;
  volume: number | string;
  volume_unit: string;
  target_price: number | string | null;
  currency: string;
  incoterms: string;
  destination_country: string;
  port_or_city: string | null;
  desired_date: string | null;
  validity_days: number;
  urgency: string;
  comment: string | null;
  assigned_to: number | null;
  ai: Record<string, unknown>;
  price_analysis: {
    target_price: number | null;
    market_avg: number | null;
    delta_pct: number | null;
    label: string | null;
  } | null;
  contact_available: boolean;
  files: Array<{
    id: number;
    file_name: string;
    mime_type: string | null;
    size_bytes: number | null;
    storage_path: string | null;
    created_at: string;
  }>;
  created_at: string;
  updated_at: string;
}

export function RequestDetailPanel() {
  const t = useTranslations("requests");
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("id");

  const isOpen = selectedId != null;

  const handleClose = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("id");
    router.replace(`?${params.toString()}`);
  }, [router, searchParams]);

  const { data, isLoading, isError } = useQuery<RequestDetail>({
    queryKey: ["request", selectedId],
    queryFn: () => apiFetch<RequestDetail>(`/requests/${selectedId}`),
    enabled: !!selectedId,
  });

  return (
    <Sheet open={isOpen} onOpenChange={(open) => { if (!open) handleClose(); }}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-[400px] max-w-[400px] bg-background-secondary border-l border-border overflow-y-auto p-0"
        role="dialog"
        aria-labelledby="request-detail-heading"
      >
        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        )}

        {isError && (
          <div className="p-4">
            <p className="text-sm text-urgency-high">
              {t("detailLoadError")}
            </p>
          </div>
        )}

        {data && (
          <div className="flex flex-col h-full">
            {/* Panel header */}
            <div className="flex flex-col gap-3 p-4 border-b border-border">
              <div className="flex items-start justify-between">
                <StatusChip status={data.status} />
                <button
                  type="button"
                  onClick={handleClose}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-foreground-muted hover:bg-background-tertiary hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                  aria-label={t("closeDetailPanel")}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              </div>
              <div>
                <p
                  id="request-detail-heading"
                  className="text-xs font-mono text-foreground-muted"
                >
                  {data.number}
                </p>
                <h2 className="text-xl font-semibold text-foreground mt-1">
                  {data.grade_text ?? t("productFallback", { id: data.product_id })}
                </h2>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  {data.polymer_type && (
                    <span className="inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs font-semibold text-foreground-muted">
                      {data.polymer_type}
                    </span>
                  )}
                  <UrgencyChip urgency={data.urgency} />
                </div>
              </div>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto">
              {/* Request Details section */}
              <section className="p-4 border-b border-border">
                <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
                  {t("sectionRequestDetails")}
                </h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  <div>
                    <dt className="text-xs text-foreground-muted">{t("fieldVolume")}</dt>
                    <dd className="text-sm font-mono text-foreground">
                      {data.volume} {data.volume_unit}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-foreground-muted">
                      {t("fieldTargetPrice")}
                    </dt>
                    <dd className="text-sm font-mono text-foreground">
                      {data.target_price != null
                        ? `${data.target_price} ${data.currency}/MT`
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-foreground-muted">
                      {t("fieldDeliveryTerms")}
                    </dt>
                    <dd className="text-sm text-foreground">
                      {data.incoterms.toUpperCase()}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-foreground-muted">
                      {t("fieldDestination")}
                    </dt>
                    <dd className="text-sm text-foreground">
                      {data.destination_country}
                      {data.port_or_city ? `, ${data.port_or_city}` : ""}
                    </dd>
                  </div>
                  {data.desired_date && (
                    <div>
                      <dt className="text-xs text-foreground-muted">
                        {t("fieldRequiredDate")}
                      </dt>
                      <dd className="text-sm text-foreground">
                        {data.desired_date}
                      </dd>
                    </div>
                  )}
                  <div>
                    <dt className="text-xs text-foreground-muted">
                      {t("fieldValidityDays")}
                    </dt>
                    <dd className="text-sm text-foreground">
                      {data.validity_days}
                    </dd>
                  </div>
                  {data.comment && (
                    <div className="col-span-2">
                      <dt className="text-xs text-foreground-muted">
                        {t("fieldAdditionalInfo")}
                      </dt>
                      <dd className="text-sm text-foreground">{data.comment}</dd>
                    </div>
                  )}
                </dl>
              </section>

              {/* Source Information section */}
              <section className="p-4 border-b border-border">
                <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
                  {t("sectionSourceInformation")}
                </h3>
                <dl className="flex flex-col gap-2">
                  <div>
                    <dt className="text-xs text-foreground-muted">{t("fieldPosted")}</dt>
                    <dd className="text-sm text-foreground">
                      <time dateTime={data.created_at}>
                        {new Date(data.created_at).toLocaleString("ru-RU", {
                          timeZone: "Asia/Tashkent",
                        })}
                      </time>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-foreground-muted">{t("fieldUpdated")}</dt>
                    <dd className="text-sm text-foreground">
                      <time dateTime={data.updated_at}>
                        {new Date(data.updated_at).toLocaleString("ru-RU", {
                          timeZone: "Asia/Tashkent",
                        })}
                      </time>
                    </dd>
                  </div>
                </dl>
              </section>

              {/* AI Analysis section */}
              <section className="p-4 border-b border-border">
                <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
                  {t("sectionAiAnalysis")}
                </h3>
                <AiAnalysisBlock
                  requestId={data.id}
                  ai={data.ai}
                  priceAnalysis={data.price_analysis}
                />
              </section>

              {/* Files section */}
              {data.files.length > 0 && (
                <section className="p-4 border-b border-border">
                  <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
                    {t("sectionFiles", { count: data.files.length })}
                  </h3>
                  <ul className="flex flex-col gap-2">
                    {data.files.map((file) => (
                      <li key={file.id} className="flex items-center gap-2">
                        <span className="text-sm text-foreground truncate flex-1">
                          {file.file_name}
                        </span>
                        {file.size_bytes != null && (
                          <span className="text-xs text-foreground-muted whitespace-nowrap">
                            {(file.size_bytes / 1024).toFixed(1)} KB
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Actions section */}
              <section className="p-4">
                <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
                  {t("sectionActions")}
                </h3>
                <RequestActions
                  requestId={data.id}
                  status={data.status}
                  contactAvailable={data.contact_available}
                  assignedTo={data.assigned_to}
                />
              </section>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
