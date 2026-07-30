import { useCallback, useEffect, useRef, useState } from "react";

import {
  complianceApi,
  useDecideSuggestion,
  useSuggestSubstance,
  type RegulationLevel,
  type SubstanceBrief,
  type SubstanceSuggestion,
} from "@/entities/compliance";

/** The six lines the «AI проверка товара» sheet ticks off, in the mockup's order. */
export const AI_CHECK_ROWS = [
  "substance",
  "cas",
  "hs",
  "dangerList",
  "circulation",
  "done",
] as const;

export type AiCheckRow = (typeof AI_CHECK_ROWS)[number];

export type AiVerdict =
  | { kind: "clear"; substance: SubstanceBrief | null }
  | { kind: "regulated"; substance: SubstanceBrief; level: RegulationLevel }
  | { kind: "unknown" };

interface AiCheckState {
  /** How many rows have been revealed. */
  revealed: number;
  running: boolean;
  verdict: AiVerdict | null;
  /** The identified row, once there is one. */
  substance: SubstanceBrief | null;
  /** What the run resolved for each line — the value printed under its title. */
  detail: Partial<Record<AiCheckRow, string>>;
  error: string | null;
}

/** Pace of the staged reveal, in ms. Fast enough not to be a wait, slow enough to read. */
const REVEAL_MS = 320;

const EMPTY: AiCheckState = {
  revealed: 0,
  running: false,
  verdict: null,
  substance: null,
  detail: {},
  error: null,
};

interface UseAiCheckOptions {
  companyId: number;
  offerId: number | null;
  /** Free text the classifier reads — product name, grade, description. */
  text: string;
  casNumber: string;
  hsCode: string;
  /** Called when the run settles on a registry row, so the draft can adopt it. */
  onIdentified: (substance: SubstanceBrief | null, cas: string, hs: string) => void;
}

/**
 * The «AI проверка товара» sheet.
 *
 * One request does the work — `POST /portal/companies/{id}/substance-suggestions`,
 * the journalled classifier the offer form already used — and the six rows are a
 * staged reveal over its single answer, not six calls. The mockup draws them
 * resolving one after another because that is what reading a verdict feels like,
 * and pretending otherwise would mean six round trips for one question.
 *
 * The seller's decision on the hint is recorded when they press «Далее»
 * ({@link confirm}): this sheet IS the confirmation, so accepting it anywhere
 * earlier would journal consent nobody gave.
 *
 * A null hint (classifier off, or the daily token budget spent) is not an error
 * — the sheet falls back to a registry search on the typed name, and failing
 * that reports honestly that the substance was not identified rather than
 * printing "не регулируется" over a thing it could not read.
 */
export function useAiCheck({
  companyId,
  offerId,
  text,
  casNumber,
  hsCode,
  onIdentified,
}: UseAiCheckOptions) {
  const suggest = useSuggestSubstance(companyId);
  const decide = useDecideSuggestion(companyId);
  const [state, setState] = useState<AiCheckState>(EMPTY);
  const suggestionRef = useRef<SubstanceSuggestion | null>(null);
  const timers = useRef<number[]>([]);

  const clearTimers = useCallback((): void => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const run = useCallback(async (): Promise<void> => {
    clearTimers();
    setState({ ...EMPTY, running: true });

    let substance: SubstanceBrief | null = null;
    let suggestedName: string | null = null;
    suggestionRef.current = null;

    try {
      const hint = await suggest.mutateAsync({ text, offerId });
      suggestionRef.current = hint;
      substance = hint?.substance ?? null;
      suggestedName = hint?.suggested_name ?? null;
      if (!substance && text.trim().length >= 2) {
        // No hint to be had: ask the registry directly. An exact-enough match on
        // the name is still an identification; anything looser is not.
        const found = await complianceApi.searchSubstances(text.trim());
        substance = found[0] ?? null;
      }
    } catch (err) {
      setState({
        ...EMPTY,
        error: err instanceof Error ? err.message : "errors.generic",
      });
      return;
    }

    const cas = substance?.cas ?? casNumber.trim();
    const hs = substance?.hs_code ?? hsCode.trim();
    const level = substance?.regulation_level ?? null;

    const verdict: AiVerdict = substance
      ? level === "free"
        ? { kind: "clear", substance }
        : { kind: "regulated", substance, level: level as RegulationLevel }
      : { kind: "unknown" };

    const detail: Partial<Record<AiCheckRow, string>> = {
      substance: substance?.name_ru ?? suggestedName ?? "",
      cas,
      hs,
    };

    onIdentified(substance, cas, hs);

    // Reveal the rows in order; the verdict panel lands with the last one.
    AI_CHECK_ROWS.forEach((_row, index) => {
      const id = window.setTimeout(
        () =>
          setState((prev) => ({
            ...prev,
            revealed: index + 1,
            substance,
            detail,
            running: index + 1 < AI_CHECK_ROWS.length,
            verdict: index + 1 === AI_CHECK_ROWS.length ? verdict : null,
          })),
        REVEAL_MS * (index + 1),
      );
      timers.current.push(id);
    });
  }, [clearTimers, suggest, text, offerId, casNumber, hsCode, onIdentified]);

  /**
   * Journal the seller's answer to the hint. Fire-and-forget: the decision is a
   * record, and a network hiccup writing it must not block a publication.
   */
  const confirm = useCallback((): void => {
    const hint = suggestionRef.current;
    if (hint === null || hint.accepted !== null) return;
    suggestionRef.current = null;
    decide.mutate({ suggestionId: hint.id, accepted: true });
  }, [decide]);

  const reset = useCallback((): void => {
    clearTimers();
    suggestionRef.current = null;
    setState(EMPTY);
  }, [clearTimers]);

  return { ...state, run, confirm, reset };
}
