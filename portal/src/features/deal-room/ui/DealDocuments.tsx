import { useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { dealApi } from "@/entities/deal";
import type { DealDetail, DealDocument, DealDocumentKind } from "@/entities/deal";
import { cn, formatDateTime } from "@/shared/lib";
import { Alert, Button, EmptyState, Select } from "@/shared/ui";

const KINDS: DealDocumentKind[] = ["contract", "invoice", "lab_passport", "transport", "other"];

interface DealDocumentsProps {
  companyId: number;
  deal: DealDetail;
  onChanged: () => void;
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Deal documents. Withdrawing marks a document revoked rather than deleting it —
 * the file stays as evidence, and the row stays visible struck through, so the
 * other side can see that something they were shown was later pulled.
 */
export function DealDocuments({ companyId, deal, onChanged }: DealDocumentsProps) {
  const { t } = useTranslation();
  const fileRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<DealDocumentKind>("other");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File | undefined): Promise<void> {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await dealApi.addDocument(companyId, deal.id, kind, file);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function open(document_: DealDocument): Promise<void> {
    const url = await dealApi.documentUrl(companyId, deal.id, document_.id);
    window.open(url, "_blank", "noopener");
  }

  async function revoke(document_: DealDocument): Promise<void> {
    const reason = window.prompt(t("deals.documents.revokePrompt"));
    if (!reason?.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await dealApi.revokeDocument(companyId, deal.id, document_.id, reason.trim());
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <Alert tone="danger" title={error} /> : null}

      <div className="flex flex-wrap items-end gap-2">
        <Select
          value={kind}
          onChange={(e) => setKind(e.target.value as DealDocumentKind)}
          aria-label={t("deals.documents.kind")}
          options={KINDS.map((k) => ({ value: k, label: t(`deals.documents.kinds.${k}`) }))}
          className="w-48"
        />
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept="application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => void upload(e.target.files?.[0])}
        />
        <Button variant="outline" loading={busy} onClick={() => fileRef.current?.click()}>
          {t("deals.documents.add")}
        </Button>
      </div>

      {deal.documents.length === 0 ? (
        <EmptyState title={t("deals.documents.empty")} description={t("deals.documents.emptyBody")} />
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {deal.documents.map((document_) => (
            <li
              key={document_.id}
              className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5"
            >
              <div className="min-w-0">
                <p
                  className={cn(
                    "truncate text-sm font-medium",
                    document_.revoked ? "text-text-subtle line-through" : "text-text",
                  )}
                >
                  {document_.file_name}
                </p>
                <p className="num text-xs text-text-subtle">
                  {t(`deals.documents.kinds.${document_.kind}`)} · {humanSize(document_.size_bytes)}{" "}
                  · {formatDateTime(document_.created_at)}
                  {document_.uploaded_by_company_name
                    ? ` · ${document_.uploaded_by_company_name}`
                    : ""}
                </p>
                {document_.revoked && document_.revoked_reason ? (
                  <p className="text-xs text-danger">
                    {t("deals.documents.revoked")}: {document_.revoked_reason}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" variant="ghost" onClick={() => void open(document_)}>
                  {t("common.open")}
                </Button>
                {!document_.revoked && document_.uploaded_by_company_id === companyId ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void revoke(document_)}
                  >
                    {t("deals.documents.revokeAction")}
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
