import { useEffect, useMemo, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { dealApi, useDeals } from "@/entities/deal";
import { contractApi, useContractTemplates } from "@/entities/contract";
import type { ContractTemplate, DirectoryCompany } from "@/entities/contract";
import { BusinessRoleBadges } from "@/entities/market";
import { ApiError } from "@/shared/api";
import {
  Alert,
  Button,
  Card,
  CardBody,
  FormField,
  Input,
  LoadingView,
  PageHeader,
  Select,
} from "@/shared/ui";

interface FieldSpec {
  key: string;
  title: string;
  enum?: string[];
  required: boolean;
}

function fieldsOf(template: ContractTemplate): FieldSpec[] {
  const schema = template.variables_schema as {
    properties?: Record<string, { title?: string; enum?: string[] }>;
    required?: string[];
  };
  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  return Object.entries(props).map(([key, spec]) => ({
    key,
    title: spec.title ?? key,
    enum: spec.enum,
    required: required.has(key),
  }));
}

export function ContractCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const offerId = searchParams.get("offerId");
  const counterpartyIdParam = searchParams.get("counterpartyId");
  // `DealDetailPage` links here with `?deal_id=`; this page used to drop it, which
  // left `deals.contract_id` NULL and stalled the deal at `contract_pending`. It is
  // only the starting value of «Основание» now — the same picker a user reaches
  // from «Договоры» directly.
  const dealIdParam = Number(searchParams.get("deal_id"));
  const [dealId, setDealId] = useState<number | null>(dealIdParam > 0 ? dealIdParam : null);
  const active = useActiveCompany().activeCompany;
  const templatesQuery = useContractTemplates();
  const dealsQuery = useDeals(active?.id ?? null, { needs_contract: true });
  const deal = dealsQuery.data?.items.find((d) => d.id === dealId) ?? null;

  const [templateId, setTemplateId] = useState<number | null>(null);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [cpQuery, setCpQuery] = useState("");
  const [cpResults, setCpResults] = useState<DirectoryCompany[]>([]);
  const [counterparty, setCounterparty] = useState<DirectoryCompany | null>(null);
  /**
   * Which rail signs this contract, frozen at creation.
   *
   * Offered rather than assumed: `didox` puts the document in front of the tax
   * authority and needs an operator account on BOTH sides, so choosing it for
   * someone who has not onboarded would fail late — after the terms were typed.
   */
  const [rail, setRail] = useState<"eimzo" | "didox">("eimzo");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const template = useMemo(
    () => templatesQuery.data?.find((tpl) => tpl.id === templateId) ?? null,
    [templatesQuery.data, templateId],
  );
  const fields = template ? fieldsOf(template) : [];

  // Seed the form from what the two parties have already agreed on the deal.
  // Only once per (deal, template), and it never overwrites the user: a field is
  // filled when blank, or when it still holds what the PREVIOUS deal put there —
  // so switching «Основание» swaps the terms over without eating anything typed.
  // A failure here is silent — a prefill that cannot be fetched must never block
  // drawing up a contract.
  const prefilledFor = useRef<string | null>(null);
  const prefilled = useRef<Record<string, string>>({});
  useEffect(() => {
    if (dealId == null || !active || !template) return;
    const token = `${dealId}:${template.id}`;
    if (prefilledFor.current === token) return;
    prefilledFor.current = token;
    let cancelled = false;
    void dealApi
      .contractPrefill(active.id, dealId, template.id)
      .then((suggested) => {
        if (cancelled) return;
        const before = prefilled.current;
        prefilled.current = suggested;
        setVariables((current) => {
          const next = { ...current };
          for (const [key, value] of Object.entries(before)) {
            if (next[key] === value) delete next[key];
          }
          for (const [key, value] of Object.entries(suggested)) {
            if (!next[key]) next[key] = value;
          }
          return next;
        });
      })
      .catch(() => {
        /* best effort — the form stays usable */
      });
    return () => {
      cancelled = true;
    };
  }, [dealId, active, template]);

  // Arriving from «Запросить контракт» on a product page: the offer hands over the
  // seller's company id, so resolve it once and preselect it. Fetched by id rather
  // than by name — the directory searches legal_name/tax_id, and a seller trading
  // under a short name would never match its own listing. An id that is no longer
  // verified comes back empty, which correctly leaves the buyer to pick by hand.
  // A deal fixes the counterparty outright: the contract links to the deal only
  // when its two parties are the deal's two parties.
  const preselectId = deal
    ? deal.counterparty.company_id
    : counterpartyIdParam
      ? Number(counterpartyIdParam)
      : null;
  useEffect(() => {
    if (preselectId == null || Number.isNaN(preselectId)) return;
    if (active && preselectId === active.id) return;
    let cancelled = false;
    void contractApi
      .directoryById(preselectId)
      .then(([match]) => {
        if (!cancelled && match) setCounterparty(match);
      })
      .catch(() => {
        /* leave the picker empty — the buyer can still search by name */
      });
    return () => {
      cancelled = true;
    };
  }, [preselectId, active]);

  async function searchCounterparties(q: string): Promise<void> {
    setCpQuery(q);
    if (q.trim().length < 2) {
      setCpResults([]);
      return;
    }
    try {
      setCpResults(await contractApi.directory(q));
    } catch {
      setCpResults([]);
    }
  }

  function missingRequired(): boolean {
    return fields.some((f) => f.required && !(variables[f.key] ?? "").trim());
  }

  async function submit(): Promise<void> {
    if (!active || !template || !counterparty) return;
    setError(null);
    setSubmitting(true);
    try {
      const created = await contractApi.create({
        initiator_company_id: active.id,
        counterparty_company_id: counterparty.id,
        template_id: template.id,
        variables,
        offer_id: offerId ? Number(offerId) : null,
        deal_id: dealId,
        signing_provider: rail,
      });
      void navigate(`/cabinet/contracts/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "company_not_verified") {
        // Typed and 403 since IMEX-7, like every other route that enforces this
        // rule. The guard below normally renders instead of the form, so this is
        // the narrow case of a verification that lapsed while the form was open —
        // and «проверьте поля» would send the user hunting through a valid form.
        setError(t("contracts.needVerifiedInitiator"));
      } else if (err instanceof ApiError && err.status === 422) {
        setError(t("contracts.errors.invalid"));
      } else {
        setError(t("contracts.errors.createFailed"));
      }
      setSubmitting(false);
    }
  }

  if (templatesQuery.isLoading) return <LoadingView label={t("common.loading")} />;

  if (!active || active.status !== "verified") {
    return (
      <Card>
        <CardBody className="space-y-3">
          <h1 className="text-xl font-semibold text-text">{t("contracts.create")}</h1>
          <Alert tone="warning">{t("contracts.needVerifiedInitiator")}</Alert>
        </CardBody>
      </Card>
    );
  }

  const dealOptions = (dealsQuery.data?.items ?? []).map((d) => ({
    value: String(d.id),
    label: [d.number, d.product, d.counterparty.name].filter(Boolean).join(" · "),
  }));
  // Arrived by `?deal_id=` for a deal the list no longer offers (it got a contract
  // meanwhile): keep the choice visible rather than showing «Без основания» while
  // still submitting the id — the server answers that with a clear 409.
  if (dealId != null && !deal && !dealsQuery.isLoading) {
    dealOptions.push({ value: String(dealId), label: `#${dealId}` });
  }

  const canSubmit = !!template && !!counterparty && !missingRequired() && !submitting;

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <PageHeader
        backTo="/cabinet/contracts"
        backLabel={t("contracts.title")}
        title={t("contracts.create")}
      />

      <Card>
        <CardBody className="space-y-4" data-testid="contract-variables">
          <FormField
            label={t("contracts.basis.label")}
            hint={dealOptions.length > 0 ? t("contracts.basis.hint") : t("contracts.basis.empty")}
          >
            {({ id }) => (
              <Select
                id={id}
                value={dealId != null ? String(dealId) : ""}
                onChange={(e) => {
                  const next = e.target.value ? Number(e.target.value) : null;
                  setDealId(next);
                  if (next == null) prefilled.current = {};
                  // A deal brings its own counterparty (the effect above resolves
                  // it when it differs); leaving the deal, its counterparty goes too.
                  if (next == null && deal) setCounterparty(null);
                }}
                options={[{ value: "", label: t("contracts.basis.none") }, ...dealOptions]}
                data-testid="contract-basis"
              />
            )}
          </FormField>

          <FormField label={t("contracts.template")} required>
            {({ id }) => (
              <Select
                id={id}
                value={templateId != null ? String(templateId) : ""}
                onChange={(e) => {
                  setTemplateId(e.target.value ? Number(e.target.value) : null);
                  setVariables({});
                  prefilled.current = {};
                }}
                options={[
                  { value: "", label: t("contracts.selectTemplate") },
                  ...(templatesQuery.data ?? []).map((tpl) => ({ value: String(tpl.id), label: tpl.name_ru })),
                ]}
              />
            )}
          </FormField>

          {template
            ? fields.map((f) => (
                <FormField key={f.key} label={f.title} required={f.required}>
                  {({ id }) =>
                    f.enum ? (
                      <Select
                        id={id}
                        value={variables[f.key] ?? ""}
                        onChange={(e) => setVariables((v) => ({ ...v, [f.key]: e.target.value }))}
                        options={[
                          { value: "", label: "—" },
                          ...f.enum.map((o) => ({ value: o, label: o })),
                        ]}
                      />
                    ) : (
                      <Input
                        id={id}
                        value={variables[f.key] ?? ""}
                        onChange={(e) => setVariables((v) => ({ ...v, [f.key]: e.target.value }))}
                      />
                    )
                  }
                </FormField>
              ))
            : null}
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <FormField label={t("contracts.rail")} hint={t(`contracts.railHint.${rail}`)}>
            {({ id }) => (
              <Select
                id={id}
                value={rail}
                onChange={(e) => setRail(e.target.value as "eimzo" | "didox")}
                options={[
                  { value: "eimzo", label: t("contracts.rails.eimzo") },
                  { value: "didox", label: t("contracts.rails.didox") },
                ]}
                data-testid="contract-rail"
              />
            )}
          </FormField>

          <FormField
            label={t("contracts.counterparty")}
            required
            hint={deal ? t("contracts.basis.counterpartyFromDeal") : t("contracts.counterpartyHint")}
          >
            {({ id }) =>
              deal ? null : (
                <Input
                  id={id}
                  value={cpQuery}
                  placeholder={t("contracts.counterpartySearch")}
                  onChange={(e) => void searchCounterparties(e.target.value)}
                />
              )
            }
          </FormField>
          {counterparty ? (
            <div className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
              <span>
                {counterparty.legal_name ?? counterparty.tax_id}{" "}
                <span className="text-text-muted">({counterparty.tax_id})</span>
              </span>
              {deal ? null : (
                <Button variant="ghost" size="sm" onClick={() => setCounterparty(null)}>
                  {t("common.cancel")}
                </Button>
              )}
            </div>
          ) : (
            <ul className="space-y-1" data-testid="cp-results">
              {cpResults
                .filter((c) => c.id !== active.id)
                .map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setCounterparty(c);
                        setCpResults([]);
                      }}
                      className="w-full rounded-md border border-border px-3 py-2 text-left text-sm hover:border-primary"
                      data-testid="cp-option"
                    >
                      {c.legal_name ?? c.tax_id}{" "}
                      <span className="text-text-muted">({c.tax_id})</span>
                      {/* Confirmed roles only — this picker chooses who to sign a
                          contract with, so the badge has to mean something. */}
                      <BusinessRoleBadges roles={c.roles} className="mt-1.5" max={3} />
                    </button>
                  </li>
                ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {error ? <Alert tone="danger">{error}</Alert> : null}

      <div className="flex justify-end gap-3">
        <Button variant="ghost" onClick={() => navigate("/cabinet/contracts")}>
          {t("common.cancel")}
        </Button>
        <Button disabled={!canSubmit} onClick={() => void submit()} data-testid="contract-submit">
          {submitting ? t("common.loading") : t("contracts.createDraft")}
        </Button>
      </div>
    </div>
  );
}
