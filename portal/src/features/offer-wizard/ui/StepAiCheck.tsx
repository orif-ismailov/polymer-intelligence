import { useCallback, useEffect, useRef } from "react";

import { useTranslation } from "react-i18next";

import { RegulationBadge } from "@/entities/compliance";
import { PRODUCT_OTHER, productLabel, useProducts } from "@/entities/product";
import { coerceLang } from "@/shared/i18n";
import { cn } from "@/shared/lib";
import {
  Alert,
  AlertCircleIcon,
  Button,
  CheckCircleOutlineIcon,
  FormField,
  Input,
  SparkIcon,
  Spinner,
  StepPanel,
} from "@/shared/ui";

import { COUNTED_STEPS, STEP_AI_CHECK } from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { AI_CHECK_ROWS, useAiCheck, type AiCheckRow } from "../model/useAiCheck";
import { StepNav } from "./StepNav";

interface StepAiCheckProps {
  companyId: number;
  onNext: () => void;
  onBack: () => void;
}

/** One line of the checklist: a mark, what is being checked, what it resolved to. */
function CheckRow({
  row,
  state,
  detail,
}: {
  row: AiCheckRow;
  state: "pending" | "running" | "done";
  detail?: string;
}) {
  const { t } = useTranslation();
  return (
    <li className="flex items-start gap-3 py-1.5" data-state={state}>
      <span className="mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center">
        {state === "done" ? (
          <span className="text-brand">
            <CheckCircleOutlineIcon size={22} />
          </span>
        ) : state === "running" ? (
          <Spinner />
        ) : (
          <span
            aria-hidden="true"
            className="block h-[18px] w-[18px] rounded-full border border-border-strong"
          />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "block text-sm",
            state === "done" ? "text-text" : "text-text-muted",
          )}
        >
          {t(`offerWizard.ai.rows.${row}`)}
        </span>
        {state === "done" && detail ? (
          <span className="num mt-0.5 block text-xs text-brand">{detail}</span>
        ) : null}
      </span>
    </li>
  );
}

/**
 * Sheet 2 — «AI проверка товара».
 *
 * Runs once when the sheet opens and again whenever the identity it read on
 * sheet 1 changes, so going back and renaming the product cannot leave a verdict
 * about the previous one on screen.
 */
export function StepAiCheck({ companyId, onNext, onBack }: StepAiCheckProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const draft = useOfferDraft((s) => s.draft);
  const patch = useOfferDraft((s) => s.patch);
  const offerId = useOfferDraft((s) => s.offerId);
  const products = useProducts();

  const catalogName =
    draft.productChoice === PRODUCT_OTHER
      ? draft.productText
      : ((products.data ?? []).find((p) => String(p.id) === draft.productChoice)
          ? productLabel(
              (products.data ?? []).find((p) => String(p.id) === draft.productChoice)!,
              lang,
            )
          : "");

  const text = [catalogName, draft.gradeText, draft.description].filter(Boolean).join(" ");

  const onIdentified = useCallback(
    (substance: Parameters<typeof patch>[0]["substance"], cas: string, hs: string) => {
      // The verdict is the source of truth for the identifiers it resolved; a
      // value the seller typed by hand survives only where the check had none.
      patch({
        substance: substance ?? null,
        casNumber: cas || draft.casNumber,
        hsCode: hs || draft.hsCode,
      });
    },
    [patch, draft.casNumber, draft.hsCode],
  );

  const check = useAiCheck({
    companyId,
    offerId,
    text,
    casNumber: draft.casNumber,
    hsCode: draft.hsCode,
    onIdentified,
  });

  // Re-run only when the product identity changes — not on every keystroke
  // elsewhere in the draft, which would restart the reveal mid-read.
  const identity = `${draft.productChoice}|${draft.productText}|${draft.gradeText}`;
  const lastIdentity = useRef<string | null>(null);
  const { run } = check;
  useEffect(() => {
    if (lastIdentity.current === identity) return;
    lastIdentity.current = identity;
    void run();
  }, [identity, run]);

  const verdict = check.verdict;
  const settled = verdict !== null;
  const needsConcentration =
    verdict?.kind === "regulated" && verdict.substance.threshold_concentration_pct !== null;

  function handleNext(): void {
    check.confirm();
    onNext();
  }

  return (
    <StepPanel
      step={STEP_AI_CHECK}
      title={t("offerWizard.ai.title")}
      counter={t("offerWizard.stepOf", { current: STEP_AI_CHECK, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-2"
    >
      <p className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
        <span className="text-brand">
          <SparkIcon size={16} />
        </span>
        {settled ? t("offerWizard.ai.finished") : t("offerWizard.ai.running")}
      </p>

      <ul className="divide-y divide-border" data-testid="offer-wizard-ai-rows">
        {AI_CHECK_ROWS.map((row, index) => (
          <CheckRow
            key={row}
            row={row}
            state={
              index < check.revealed ? "done" : index === check.revealed && check.running ? "running" : "pending"
            }
            detail={check.detail[row]}
          />
        ))}
      </ul>

      {check.error ? (
        <Alert tone="danger" className="mt-4" title={t("errors.generic")}>
          <Button size="sm" variant="ghost" onClick={() => void check.run()}>
            {t("common.retry")}
          </Button>
        </Alert>
      ) : null}

      {/* The verdict panel — green when nothing regulates the goods, which is
          the mockup's case; otherwise it says what publishing will require. */}
      {verdict?.kind === "clear" ? (
        <div
          className="mt-4 rounded-md border border-brand-line bg-brand-soft px-4 py-3"
          data-testid="offer-wizard-verdict"
          data-verdict="clear"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-brand">
            <CheckCircleOutlineIcon size={18} />
            {t("offerWizard.ai.clearTitle")}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-text-muted">
            {t("offerWizard.ai.clearBody")}
          </p>
        </div>
      ) : null}

      {verdict?.kind === "regulated" ? (
        <div
          className="mt-4 rounded-md border border-gold-line bg-gold-soft px-4 py-3"
          data-testid="offer-wizard-verdict"
          data-verdict="regulated"
        >
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text">
            <span className="text-gold">
              <AlertCircleIcon size={18} />
            </span>
            {verdict.substance.name_ru}
            <RegulationBadge level={verdict.level} />
          </p>
          <p className="mt-1 text-xs leading-relaxed text-text-muted">
            {t(`offerWizard.ai.regulated.${verdict.level}`)}
          </p>
        </div>
      ) : null}

      {verdict?.kind === "unknown" ? (
        <Alert tone="info" className="mt-4" title={t("offerWizard.ai.unknownTitle")} data-testid="offer-wizard-verdict">
          {t("offerWizard.ai.unknownBody")}
        </Alert>
      ) : null}

      {/* Concentration decides whether a regime applies at all (acetone is a
          precursor at ≥60%), so it is asked for only when it can change the
          answer — and never on the mockup's happy path. */}
      {needsConcentration ? (
        <FormField
          className="mt-4"
          label={t("compliance.concentration")}
          hint={t("compliance.concentrationHint")}
        >
          {({ id }) => (
            <Input
              id={id}
              inputMode="decimal"
              value={draft.concentration}
              onChange={(e) => patch({ concentration: e.target.value })}
            />
          )}
        </FormField>
      ) : null}

      <StepNav onNext={handleNext} onBack={onBack} disabled={!settled} />
    </StepPanel>
  );
}
