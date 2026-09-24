"use client";

/**
 * Bank register (/admin/bank-register)
 *
 * The Central Bank publishes its branch register as an .xlsx; «Код филиала» is the
 * 5-digit MFO a company types on the registration bank step, and the register is
 * what turns that number into a bank name. It is republished periodically, so this
 * screen exists to reload it WITHOUT a deploy.
 *
 * Access is the `adminBankRegister` page grant (see `lib/nav.ts` and
 * `backend/app/core/pages.py`); the (dashboard) layout already gates the route from
 * the nav, so there is no in-page redirect here.
 */

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Landmark, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { ApiError, apiFetch, apiUpload } from "@/lib/api";
import { formatTashkent } from "@/lib/tz";

interface RegisterStatus {
  loaded: boolean;
  row_count: number;
  filename: string | null;
  file_created_at: string | null;
  uploaded_at: string | null;
  uploaded_by: string | null;
}

interface ImportResult {
  imported: boolean;
  row_count: number;
  file_created_at: string | null;
}

export default function BankRegisterPage() {
  const t = useTranslations("adminBankRegister");
  const qc = useQueryClient();
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A file input keeps showing the filename it displayed even after React state is
  // cleared, so it would advertise a file it is not going to send. Remounting it is
  // the only way to clear what the user sees.
  const [fileKey, setFileKey] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  const status = useQuery({
    queryKey: ["bank-register"],
    queryFn: () => apiFetch<RegisterStatus>("/admin/bank-register"),
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiUpload<ImportResult>("/admin/bank-register", form);
    },
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setFileKey((n) => n + 1);
      void qc.invalidateQueries({ queryKey: ["bank-register"] });
    },
    onError: (err: unknown) => {
      setResult(null);
      // The backend's 422 detail is the parser's own reason (`not_a_zip`,
      // `header_row_not_found`, `bad_mfo:123`) — far more useful than a generic
      // failure line, so it is shown rather than swallowed.
      const detail =
        err instanceof ApiError && typeof (err.body as { detail?: unknown })?.detail === "string"
          ? ((err.body as { detail: string }).detail)
          : null;
      setError(detail ?? t("failed"));
      setFileKey((n) => n + 1);
    },
  });

  const s = status.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t("title")}</h1>
        <p className="mt-1 text-sm text-foreground-muted">{t("subtitle")}</p>
      </div>

      {status.isLoading ? (
        <div className="space-y-3">
          <div className="h-24 animate-pulse rounded-lg bg-background-tertiary" />
        </div>
      ) : status.isError ? (
        <div className="rounded-md border border-urgency-high/30 bg-urgency-high/10 p-4 text-sm text-foreground">
          {t("failed")}
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-background-secondary p-5">
          <div className="flex items-start gap-3">
            <Landmark className="mt-0.5 h-5 w-5 text-foreground-muted" aria-hidden />
            <div className="flex-1">
              <p className="text-sm font-medium text-foreground">
                {s?.loaded ? t("loaded") : t("notLoaded")}
              </p>
              {s?.loaded ? (
                <dl className="mt-3 grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
                  <div className="flex justify-between gap-4 sm:block">
                    <dt className="text-foreground-muted">{t("rows")}</dt>
                    <dd className="num text-foreground">{s.row_count}</dd>
                  </div>
                  <div className="flex justify-between gap-4 sm:block">
                    <dt className="text-foreground-muted">{t("fileDate")}</dt>
                    <dd className="num text-foreground">{s.file_created_at ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between gap-4 sm:block">
                    <dt className="text-foreground-muted">{t("uploadedAt")}</dt>
                    <dd className="text-foreground">
                      {s.uploaded_at ? formatTashkent(s.uploaded_at) : "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4 sm:block">
                    <dt className="text-foreground-muted">{t("uploadedBy")}</dt>
                    {/* No uploader means the copy that shipped with the release —
                        a fact worth stating, not an empty cell. */}
                    <dd className="text-foreground">{s.uploaded_by ?? t("shipped")}</dd>
                  </div>
                  <div className="col-span-full flex justify-between gap-4 sm:block">
                    <dt className="text-foreground-muted">{t("file")}</dt>
                    <dd className="text-foreground">{s.filename ?? "—"}</dd>
                  </div>
                </dl>
              ) : null}
            </div>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-background-secondary p-5">
        <input
          key={fileKey}
          ref={fileRef}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={upload.isPending}
          onClick={() => fileRef.current?.click()}
          className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90 disabled:opacity-50"
        >
          <Upload className="h-4 w-4" aria-hidden />
          {upload.isPending ? t("uploading") : t("upload")}
        </button>
        <p className="mt-2 text-sm text-foreground-muted">{t("hint")}</p>

        {result ? (
          <div className="mt-4 rounded-md border border-border bg-background p-3 text-sm text-foreground">
            {result.imported ? t("imported", { count: result.row_count }) : t("unchanged")}
          </div>
        ) : null}
        {error ? (
          <div className="mt-4 rounded-md border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-foreground">
            {error}
          </div>
        ) : null}
      </div>
    </div>
  );
}
