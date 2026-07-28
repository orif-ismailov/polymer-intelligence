import { useState } from "react";

import { useTranslation } from "react-i18next";

import {
  RegulationBadge,
  useDecideSuggestion,
  useSubstanceSearch,
  useSuggestSubstance,
} from "@/entities/compliance";
import type { SubstanceBrief } from "@/entities/compliance";
import { Alert, Badge, Button, FormField, Input, Spinner } from "@/shared/ui";

interface SubstanceFieldProps {
  companyId: number;
  /** Chosen registry row, or null when the seller types identifiers by hand. */
  substance: SubstanceBrief | null;
  casNumber: string;
  hsCode: string;
  concentration: string;
  /** Free text the AI hint reads (product name + description). */
  offerText: string;
  offerId: number | null;
  onPick: (substance: SubstanceBrief | null) => void;
  onCas: (value: string) => void;
  onHs: (value: string) => void;
  onConcentration: (value: string) => void;
}

/**
 * The chemistry block of the offer form (FR-C2/C3).
 *
 * Three ways in, in order of how much they pin down:
 *   1. pick from the registry — fills CAS/HS and shows what publishing will
 *      require, so a licence is news at the top of the form and not at the save;
 *   2. ask the AI which substance the description is about — a suggestion the
 *      seller confirms or rejects, never an auto-fill;
 *   3. type CAS/HS by hand for something the registry does not carry yet.
 */
export function SubstanceField({
  companyId,
  substance,
  casNumber,
  hsCode,
  concentration,
  offerText,
  offerId,
  onPick,
  onCas,
  onHs,
  onConcentration,
}: SubstanceFieldProps) {
  const { t } = useTranslation();
  const [term, setTerm] = useState("");
  const results = useSubstanceSearch(term);
  const suggest = useSuggestSubstance(companyId);
  const decide = useDecideSuggestion(companyId);
  const [noHint, setNoHint] = useState(false);

  const suggestion = suggest.data ?? null;
  const undecided = suggestion !== null && suggestion.accepted === null;

  function choose(row: SubstanceBrief): void {
    onPick(row);
    onCas(row.cas ?? "");
    onHs(row.hs_code);
    setTerm("");
  }

  function askAi(): void {
    setNoHint(false);
    suggest.mutate(
      { text: offerText, offerId },
      { onSuccess: (row) => setNoHint(row === null) },
    );
  }

  function answer(accepted: boolean): void {
    if (suggestion === null) return;
    decide.mutate(
      { suggestionId: suggestion.id, accepted },
      {
        onSuccess: (row) => {
          suggest.reset();
          if (accepted && row.substance) choose(row.substance);
        },
      },
    );
  }

  return (
    <fieldset className="space-y-4 rounded-lg border border-border p-4">
      <legend className="px-1 text-sm font-medium text-text">{t("compliance.title")}</legend>
      <p className="text-xs text-text-muted">{t("compliance.hint")}</p>

      {substance ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-surface-2 px-3 py-2">
          <span className="text-sm font-medium text-text">{substance.name_ru}</span>
          <Badge tone="neutral">{substance.hs_code}</Badge>
          {substance.cas ? <Badge tone="neutral">CAS {substance.cas}</Badge> : null}
          <RegulationBadge level={substance.regulation_level} />
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => onPick(null)}
          >
            {t("common.clear")}
          </Button>
        </div>
      ) : (
        <>
          <FormField label={t("compliance.search")} hint={t("compliance.searchHint")}>
            {({ id }) => (
              <Input
                id={id}
                value={term}
                placeholder={t("compliance.searchPlaceholder")}
                onChange={(e) => setTerm(e.target.value)}
              />
            )}
          </FormField>

          {results.isFetching ? (
            <p className="flex items-center gap-2 text-sm text-text-muted">
              <Spinner /> {t("common.loading")}
            </p>
          ) : null}

          {results.data && results.data.length > 0 ? (
            <ul className="divide-y divide-border rounded-md border border-border">
              {results.data.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-surface-2"
                    onClick={() => choose(row)}
                  >
                    <span className="text-sm text-text">{row.name_ru}</span>
                    <span className="text-xs text-text-muted">{row.hs_code}</span>
                    <span className="ml-auto">
                      <RegulationBadge level={row.regulation_level} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          {results.data && results.data.length === 0 && term.trim().length >= 2 ? (
            <p className="text-sm text-text-muted">{t("compliance.searchEmpty")}</p>
          ) : null}
        </>
      )}

      {/* AI hint — offered only when there is text to read. */}
      {!substance ? (
        <div className="space-y-2">
          <Button
            size="sm"
            variant="outline"
            onClick={askAi}
            disabled={offerText.trim().length < 3}
            loading={suggest.isPending}
          >
            {t("compliance.askAi")}
          </Button>
          {noHint ? <p className="text-sm text-text-muted">{t("compliance.aiNoHint")}</p> : null}
          {undecided && suggestion ? (
            <Alert tone="info" title={t("compliance.aiSuggestion")}>
              <div className="space-y-2">
                <p className="text-sm">
                  <span className="font-medium">{suggestion.suggested_name}</span>
                  {suggestion.suggested_cas ? ` · CAS ${suggestion.suggested_cas}` : ""}
                  {suggestion.suggested_hs_code ? ` · ${suggestion.suggested_hs_code}` : ""}
                </p>
                {suggestion.substance === null ? (
                  <p className="text-xs">{t("compliance.aiUnknownSubstance")}</p>
                ) : null}
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => answer(true)} loading={decide.isPending}>
                    {t("compliance.aiAccept")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => answer(false)}>
                    {t("compliance.aiReject")}
                  </Button>
                </div>
              </div>
            </Alert>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label={t("compliance.cas")}>
          {({ id }) => (
            <Input
              id={id}
              value={casNumber}
              disabled={substance !== null}
              onChange={(e) => onCas(e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("compliance.hs")}>
          {({ id }) => (
            <Input
              id={id}
              value={hsCode}
              disabled={substance !== null}
              onChange={(e) => onHs(e.target.value)}
            />
          )}
        </FormField>
        {/* Concentration decides whether a regime applies at all (acetone is a
            precursor at ≥60%), so it is asked for even without a registry row. */}
        <FormField label={t("compliance.concentration")} hint={t("compliance.concentrationHint")}>
          {({ id }) => (
            <Input
              id={id}
              inputMode="decimal"
              value={concentration}
              onChange={(e) => onConcentration(e.target.value)}
            />
          )}
        </FormField>
      </div>
    </fieldset>
  );
}
