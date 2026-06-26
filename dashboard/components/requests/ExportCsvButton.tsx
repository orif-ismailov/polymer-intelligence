"use client";

/**
 * ExportCsvButton — triggers GET /api/v1/requests/export with current URL filters.
 *
 * Uses window.location.href to start the CSV download (browser handles the
 * Content-Disposition: attachment response). Attaches the current JWT from
 * the in-memory token store via a fetch() call that re-uses the response as
 * a blob download, since <a href> cannot send Authorization headers.
 *
 * UI-SPEC Export button behavior: CSV, current filtered result set, all columns.
 * Copywriting: "Export CSV".
 * No hardcoded hex — token classes only.
 */

import { useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Download } from "lucide-react";
import { ApiError } from "@/lib/api";

export function ExportCsvButton() {
  const t = useTranslations("requests");
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Build export URL with current filter params (same filters as the table)
      const params = new URLSearchParams();
      const status = searchParams.get("status");
      const urgency = searchParams.get("urgency");
      const product = searchParams.get("product");

      if (status) params.set("status", status);
      if (urgency) params.set("urgency", urgency);
      if (product) params.set("product_id", product);

      const qs = params.toString();
      const path = `/requests/export${qs ? `?${qs}` : ""}`;

      // Use apiFetch with a raw fetch approach for binary/streaming response
      // We use getToken() to attach the Bearer token and handle the download.
      const { getToken } = await import("@/lib/api");
      const token = getToken();

      const response = await fetch(`/api/v1${path}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new ApiError(
          response.status,
          null,
          t("exportError"),
        );
      }

      // Download as file
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "requests.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : t("exportError");
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [searchParams, t]);

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={handleExport}
        disabled={isLoading}
        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background-secondary px-3 text-sm text-foreground hover:bg-background-tertiary disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        aria-label={t("exportAriaLabel")}
      >
        {isLoading ? (
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-foreground-muted border-t-transparent" />
        ) : (
          <Download size={14} aria-hidden="true" />
        )}
        {t("exportCsv")}
      </button>
      {error && (
        <p className="text-xs text-urgency-high" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
