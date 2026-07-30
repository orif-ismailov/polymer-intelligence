import { useTranslation } from "react-i18next";

import { formatBytes } from "@/shared/lib";
import { CloseIcon, Dropzone, FileIcon, IconButton } from "@/shared/ui";

import { COUNTED_STEPS, FACTORY_RFQ_DOC_KINDS, STEP_DOCUMENTS } from "../model/constants";
import { useFactoryRfqDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepDocumentsProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Sheet 2 — five compliance-document slots by kind, one file each.
 *
 * All optional: nothing here blocks «Далее» — a buyer can submit the RFQ and
 * attach documents later straight from the factory's chat or the RFQ record.
 */
export function StepDocuments({ onNext, onBack }: StepDocumentsProps) {
  const { t } = useTranslation();
  const documents = useFactoryRfqDraft((s) => s.draft.documents);
  const setDocument = useFactoryRfqDraft((s) => s.setDocument);

  return (
    <div className="space-y-5" data-testid="factory-rfq-step-2">
      <header>
        <p className="num text-xs text-text-muted">
          {t("factoryRfq.stepOf", { current: STEP_DOCUMENTS, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">{t("factoryRfq.documents.title")}</h2>
        <p className="mt-1 text-sm text-text-muted">{t("factoryRfq.documents.subtitle")}</p>
      </header>

      <div className="space-y-4">
        {FACTORY_RFQ_DOC_KINDS.map((kind) => {
          const file = documents[kind];
          return (
            <div key={kind}>
              <p className="mb-2 text-sm font-medium text-text">
                {t(`factoryRfq.documents.kinds.${kind}`)}
              </p>
              {file ? (
                <div className="flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2.5">
                  <span className="shrink-0 text-brand">
                    <FileIcon size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-text">{file.name}</p>
                    <p className="num text-xs text-text-subtle">
                      {t("factoryRfq.documents.uploaded")} · {formatBytes(file.size)}
                    </p>
                  </div>
                  <IconButton
                    label={t("factoryRfq.documents.remove")}
                    onClick={() => setDocument(kind, null)}
                  >
                    <CloseIcon size={16} />
                  </IconButton>
                </div>
              ) : (
                <Dropzone
                  label={t("factoryRfq.documents.dropLabel")}
                  hint={t("factoryRfq.documents.dropHint")}
                  accept="application/pdf,image/jpeg,image/png"
                  onFiles={(files) => setDocument(kind, files[0] ?? null)}
                  data-testid={`factory-rfq-doc-${kind}`}
                />
              )}
            </div>
          );
        })}
      </div>

      <StepNav onNext={onNext} onBack={onBack} />
    </div>
  );
}
