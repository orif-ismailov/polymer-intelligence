import { type ChangeEvent, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import {
  companyApi,
  useRemoveCompanyDocument,
  useUploadCompanyDocument,
} from "@/entities/company";
import type { CompanyDetail, DocumentMeta } from "@/entities/company";
import { DOCUMENT_KINDS, MAX_UPLOAD_BYTES } from "@/shared/config";
import { coerceLang, useEnumLabels } from "@/shared/i18n";
import { formatBytes, formatDate } from "@/shared/lib";
import { useAuthStore } from "@/entities/account";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  FormField,
  Select,
  Spinner,
} from "@/shared/ui";

interface DocumentsSectionProps {
  company: CompanyDetail;
  editable: boolean;
}

function DocumentRow({
  document,
  companyId,
  editable,
  lang,
  onRemove,
}: {
  document: DocumentMeta;
  companyId: number;
  editable: boolean;
  lang: string;
  onRemove: (id: number) => void;
}) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const [downloading, setDownloading] = useState(false);

  async function download(): Promise<void> {
    setDownloading(true);
    try {
      const url = await companyApi.documentDownloadUrl(companyId, document.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } finally {
      setDownloading(false);
    }
  }

  const removable = editable && document.status === "pending_review";

  return (
    <li className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-text">{label("documentKind", document.kind)}</p>
        <p className="text-xs text-text-muted">
          {formatBytes(document.size_bytes)} · {formatDate(document.created_at, lang)}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <Badge tone={document.status === "approved" ? "success" : "neutral"}>{document.status}</Badge>
        <button
          type="button"
          onClick={() => void download()}
          className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
        >
          {downloading ? <Spinner /> : null}
          {t("common.download")}
        </button>
        {removable ? (
          <button
            type="button"
            onClick={() => onRemove(document.id)}
            className="text-xs font-medium text-danger hover:underline"
          >
            {t("common.remove")}
          </button>
        ) : null}
      </div>
    </li>
  );
}

export function DocumentsSection({ company, editable }: DocumentsSectionProps) {
  const { t } = useTranslation();
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const upload = useUploadCompanyDocument(company.id);
  const remove = useRemoveCompanyDocument(company.id);
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<string>(DOCUMENT_KINDS[0]);
  const [removeId, setRemoveId] = useState<number | null>(null);
  const [sizeError, setSizeError] = useState<string | null>(null);

  function handleFile(e: ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setSizeError(t("wizard.documents.tooLarge"));
      return;
    }
    setSizeError(null);
    upload.mutate({ kind, file });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("company.documents")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {company.documents.length > 0 ? (
          <ul className="divide-y divide-border">
            {company.documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                companyId={company.id}
                editable={editable}
                lang={lang}
                onRemove={setRemoveId}
              />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-muted">{t("company.noDocuments")}</p>
        )}

        {editable ? (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-surface-2 p-4 sm:flex-row sm:items-end">
            <FormField label={t("company.documentKind")} className="sm:max-w-xs">
              {({ id }) => (
                <Select
                  id={id}
                  value={kind}
                  options={DOCUMENT_KINDS.map((k) => ({ value: k, label: k }))}
                  onChange={(e) => setKind(e.target.value)}
                />
              )}
            </FormField>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,image/jpeg,image/png"
              className="sr-only"
              onChange={handleFile}
            />
            <Button variant="outline" onClick={() => inputRef.current?.click()} loading={upload.isPending}>
              {t("company.uploadDocument")}
            </Button>
          </div>
        ) : null}

        {sizeError ? <Alert tone="danger" title={sizeError} /> : null}
        {upload.isError ? <Alert tone="danger" title={t("errors.generic")}>{upload.error.message}</Alert> : null}
      </CardBody>

      <ConfirmDialog
        open={removeId !== null}
        title={t("company.removeDocument")}
        description={t("company.removeDocumentConfirm")}
        confirmLabel={t("common.remove")}
        cancelLabel={t("common.cancel")}
        danger
        loading={remove.isPending}
        onClose={() => setRemoveId(null)}
        onConfirm={() => {
          if (removeId !== null) remove.mutate(removeId, { onSuccess: () => setRemoveId(null) });
        }}
      />
    </Card>
  );
}
