import { useTranslation } from "react-i18next";

import { Checkbox, FormField, Textarea } from "@/shared/ui";

import {
  COMMENT_MAX,
  COUNTED_STEPS,
  REQUEST_DOC_KINDS,
  SPECS_MAX,
  STEP_EXTRA,
  type RequestDocKind,
} from "../model/constants";
import { useRequestDraft } from "../model/draftStore";
import { StepNav } from "./StepNav";

interface StepExtraProps {
  onNext: () => void;
  onBack: () => void;
}

/**
 * Sheet 3 — «Дополнительные параметры»: specs textarea, document checklist,
 * free-form comments. Everything on this sheet is optional.
 */
export function StepExtra({ onNext, onBack }: StepExtraProps) {
  const { t } = useTranslation();
  const draft = useRequestDraft((s) => s.draft);
  const setField = useRequestDraft((s) => s.setField);
  const toggleDoc = useRequestDraft((s) => s.toggleDoc);

  return (
    <div className="space-y-5" data-testid="request-wizard-step-3">
      <header>
        <p className="num text-xs text-text-muted">
          {t("requestWizard.stepOf", { current: STEP_EXTRA, total: COUNTED_STEPS })}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-text">
          {t("requestWizard.extra.title")}
        </h2>
      </header>

      <FormField label={t("requestWizard.extra.specs")}>
        {({ id }) => (
          <div>
            <Textarea
              id={id}
              rows={4}
              maxLength={SPECS_MAX}
              value={draft.specs}
              onChange={(e) => setField("specs", e.target.value)}
              placeholder={t("requestWizard.extra.specsPlaceholder")}
              data-testid="request-wizard-specs"
            />
            <p className="num mt-1 text-end text-xs text-text-subtle">
              {draft.specs.length}/{SPECS_MAX}
            </p>
          </div>
        )}
      </FormField>

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-text">
          {t("requestWizard.extra.docs")}
        </legend>
        <ul className="space-y-2">
          {REQUEST_DOC_KINDS.map((kind: RequestDocKind) => (
            <li key={kind}>
              <Checkbox
                id={`req-doc-${kind}`}
                label={t(`requestWizard.extra.doc.${kind}`)}
                description={
                  kind === "other" ? t("requestWizard.extra.docOtherHint") : undefined
                }
                checked={draft.requiredDocs.includes(kind)}
                onChange={() => toggleDoc(kind)}
                data-testid={`request-wizard-doc-${kind}`}
              />
            </li>
          ))}
        </ul>
      </fieldset>

      <FormField label={t("requestWizard.extra.comment")}>
        {({ id }) => (
          <div>
            <Textarea
              id={id}
              rows={4}
              maxLength={COMMENT_MAX}
              value={draft.comment}
              onChange={(e) => setField("comment", e.target.value)}
              placeholder={t("requestWizard.extra.commentPlaceholder")}
              data-testid="request-wizard-comment"
            />
            <p className="num mt-1 text-end text-xs text-text-subtle">
              {draft.comment.length}/{COMMENT_MAX}
            </p>
          </div>
        )}
      </FormField>

      <StepNav onNext={onNext} onBack={onBack} />
    </div>
  );
}
