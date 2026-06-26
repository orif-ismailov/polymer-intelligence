"use client";

/**
 * RuleBuilder — form for creating/managing alert rules.
 *
 * Fields:
 * - Rule name (required)
 * - Kind multiselect (buy_request/sell_offer/deal/price_quote)
 * - Product select (all or specific product_id)
 * - Volume >= (number, MT)
 * - Urgency checkbox group (high/medium/low)
 * - Source kind multiselect
 * - Lead Score >= (DISABLED, labeled "Activates with Phase 5 AI", D-07)
 * - Delivery chat_id(s): textarea, one per line (D-08)
 * - Urgency channel: DM / Group
 *
 * Existing rules list with predicate summary + delete (AlertDialog confirm).
 *
 * No hardcoded hex.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, AlertCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface AlertRuleOut {
  id: number;
  kind: string;
  name: string;
  condition: Record<string, unknown>;
  channels: Array<Record<string, unknown>>;
  is_enabled: boolean;
  created_by: number | null;
  created_at: string;
}

type KindValue = "buy_request" | "sell_offer" | "deal" | "price_quote";
type UrgencyValue = "high" | "medium" | "low";

const KIND_OPTIONS: { value: KindValue; labelKey: string }[] = [
  { value: "buy_request", labelKey: "kindOptions.buy_request" },
  { value: "sell_offer", labelKey: "kindOptions.sell_offer" },
  { value: "deal", labelKey: "kindOptions.deal" },
  { value: "price_quote", labelKey: "kindOptions.price_quote" },
];

const URGENCY_OPTIONS: { value: UrgencyValue; labelKey: string }[] = [
  { value: "high", labelKey: "urgencyOptions.high" },
  { value: "medium", labelKey: "urgencyOptions.medium" },
  { value: "low", labelKey: "urgencyOptions.low" },
];

// Product labels are proper nouns (polymer grades) and stay untranslated;
// the "All Products" sentinel (empty value) is translated at render.
const PRODUCT_OPTIONS = [
  { value: "", label: "All Products" },
  { value: "1", label: "PP Raffia" },
  { value: "2", label: "HDPE" },
  { value: "3", label: "LDPE" },
  { value: "4", label: "LLDPE" },
  { value: "5", label: "PVC" },
  { value: "6", label: "PET" },
  { value: "7", label: "PS" },
  { value: "8", label: "ABS" },
];

const SOURCE_KIND_OPTIONS = [
  { value: "html_table", labelKey: "sourceKindOptions.html_table" },
  { value: "rss", labelKey: "sourceKindOptions.rss" },
  { value: "telegram_channel", labelKey: "sourceKindOptions.telegram_channel" },
  { value: "llm_page", labelKey: "sourceKindOptions.llm_page" },
  { value: "uzex_offers", labelKey: "sourceKindOptions.uzex_offers" },
  { value: "uzex_contracts", labelKey: "sourceKindOptions.uzex_contracts" },
  { value: "uzex_deals", labelKey: "sourceKindOptions.uzex_deals" },
  { value: "webapp", labelKey: "sourceKindOptions.webapp" },
];

// ─── Predicate summary ────────────────────────────────────────────────────────

function PredicateSummary({ condition }: { condition: Record<string, unknown> }) {
  const t = useTranslations("alerts");
  const parts: string[] = [];
  if (condition.kind) parts.push(t("predicate.kind", { value: (condition.kind as string[]).join(", ") }));
  if (condition.product_id) parts.push(t("predicate.product", { id: condition.product_id as number }));
  if (condition.volume_gte) parts.push(t("predicate.volume", { value: condition.volume_gte as number }));
  if (condition.urgency_in) parts.push(t("predicate.urgency", { value: (condition.urgency_in as string[]).join(", ") }));
  if (condition.source_kind) parts.push(t("predicate.source", { value: (condition.source_kind as string[]).join(", ") }));
  if (parts.length === 0) parts.push(t("predicate.any"));
  return <span className="text-xs text-foreground-muted">{parts.join(" · ")}</span>;
}

// ─── Delete confirm dialog ────────────────────────────────────────────────────

function DeleteRuleDialog({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("alerts");
  return (
    <AlertDialog open={open}>
      <AlertDialogContent className="bg-background-secondary border-border">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-foreground">{t("deleteDialog.title")}</AlertDialogTitle>
          <AlertDialogDescription className="text-foreground-muted">
            {t("deleteDialog.description")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            onClick={onCancel}
            className="border-border bg-transparent text-foreground hover:bg-background-tertiary"
          >
            {t("deleteDialog.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-status-cancelled text-white hover:bg-status-cancelled/80"
          >
            {t("deleteDialog.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ─── Rule form ────────────────────────────────────────────────────────────────

interface RuleFormState {
  name: string;
  kinds: KindValue[];
  productId: string;
  volumeGte: string;
  urgencies: UrgencyValue[];
  sourceKinds: string[];
  chatIds: string;
  urgencyChannel: "dm" | "group";
}

function RuleForm({
  onSave,
  onCancel,
  isSaving,
}: {
  onSave: (state: RuleFormState) => void;
  onCancel: () => void;
  isSaving: boolean;
}) {
  const t = useTranslations("alerts");
  const [form, setForm] = useState<RuleFormState>({
    name: "",
    kinds: [],
    productId: "",
    volumeGte: "",
    urgencies: [],
    sourceKinds: [],
    chatIds: "",
    urgencyChannel: "dm",
  });
  const [nameError, setNameError] = useState("");

  function toggleKind(v: KindValue) {
    setForm((prev) => ({
      ...prev,
      kinds: prev.kinds.includes(v) ? prev.kinds.filter((k) => k !== v) : [...prev.kinds, v],
    }));
  }

  function toggleUrgency(v: UrgencyValue) {
    setForm((prev) => ({
      ...prev,
      urgencies: prev.urgencies.includes(v) ? prev.urgencies.filter((u) => u !== v) : [...prev.urgencies, v],
    }));
  }

  function toggleSourceKind(v: string) {
    setForm((prev) => ({
      ...prev,
      sourceKinds: prev.sourceKinds.includes(v)
        ? prev.sourceKinds.filter((s) => s !== v)
        : [...prev.sourceKinds, v],
    }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setNameError(t("form.nameRequired"));
      return;
    }
    setNameError("");
    onSave(form);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Rule name */}
      <div className="flex flex-col gap-1">
        <label htmlFor="rule-name" className="text-xs font-semibold text-foreground-muted">
          {t("form.nameLabel")} <span className="text-urgency-high">*</span>
        </label>
        <input
          id="rule-name"
          type="text"
          value={form.name}
          onChange={(e) => { setForm((p) => ({ ...p, name: e.target.value })); if (nameError) setNameError(""); }}
          placeholder={t("form.namePlaceholder")}
          className={`rounded-md border ${nameError ? "border-urgency-high" : "border-border"} bg-background-tertiary px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary`}
        />
        {nameError && <p className="text-xs text-urgency-high">{nameError}</p>}
      </div>

      {/* Kind multiselect */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-semibold text-foreground-muted">{t("form.signalKindLabel")}</label>
        <div className="flex flex-wrap gap-2">
          {KIND_OPTIONS.map(({ value, labelKey }) => (
            <button
              key={value}
              type="button"
              onClick={() => toggleKind(value)}
              className={`rounded-full px-3 py-1 text-xs font-semibold border transition-colors ${
                form.kinds.includes(value)
                  ? "bg-accent text-white border-accent"
                  : "bg-background-tertiary text-foreground-muted border-border hover:border-accent/50"
              }`}
            >
              {t(labelKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Product */}
      <div className="flex flex-col gap-1">
        <label htmlFor="rule-product" className="text-xs font-semibold text-foreground-muted">{t("form.productLabel")}</label>
        <select
          id="rule-product"
          value={form.productId}
          onChange={(e) => setForm((p) => ({ ...p, productId: e.target.value }))}
          className="rounded-md border border-border bg-background-tertiary px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary"
        >
          {PRODUCT_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>{value === "" ? t("form.allProducts") : label}</option>
          ))}
        </select>
      </div>

      {/* Volume >= */}
      <div className="flex flex-col gap-1">
        <label htmlFor="rule-volume" className="text-xs font-semibold text-foreground-muted">{t("form.volumeLabel")}</label>
        <input
          id="rule-volume"
          type="number"
          min="0"
          step="any"
          value={form.volumeGte}
          onChange={(e) => setForm((p) => ({ ...p, volumeGte: e.target.value }))}
          placeholder={t("form.volumePlaceholder")}
          className="rounded-md border border-border bg-background-tertiary px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary"
        />
      </div>

      {/* Urgency checkboxes */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-semibold text-foreground-muted">{t("form.urgencyLabel")}</label>
        <div className="flex gap-4">
          {URGENCY_OPTIONS.map(({ value, labelKey }) => (
            <label key={value} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={form.urgencies.includes(value)}
                onChange={() => toggleUrgency(value)}
                className="h-4 w-4 rounded border-border bg-background-tertiary text-accent focus:ring-accent"
              />
              {t(labelKey)}
            </label>
          ))}
        </div>
      </div>

      {/* Source kind multiselect */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-semibold text-foreground-muted">{t("form.sourceKindLabel")}</label>
        <div className="flex flex-wrap gap-2">
          {SOURCE_KIND_OPTIONS.map(({ value, labelKey }) => (
            <button
              key={value}
              type="button"
              onClick={() => toggleSourceKind(value)}
              className={`rounded-full px-3 py-1 text-xs font-semibold border transition-colors ${
                form.sourceKinds.includes(value)
                  ? "bg-accent text-white border-accent"
                  : "bg-background-tertiary text-foreground-muted border-border hover:border-accent/50"
              }`}
            >
              {t(labelKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Lead Score >= (DISABLED — Phase 5, D-07) */}
      <TooltipProvider>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <label htmlFor="rule-lead-score" className="text-xs font-semibold text-foreground-muted">
              {t("form.leadScoreLabel")}
            </label>
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-400">
              <AlertCircle size={12} aria-hidden="true" />
              {t("form.leadScoreBadge")}
            </span>
          </div>
          <Tooltip>
            <TooltipTrigger render={
              <input
                id="rule-lead-score"
                type="number"
                min="0"
                max="1"
                step="0.01"
                disabled
                placeholder={t("form.leadScorePlaceholder")}
                className="rounded-md border border-border bg-background-tertiary/50 px-3 py-2 text-sm text-foreground-subtle placeholder:text-foreground-subtle cursor-not-allowed opacity-50 focus:outline-none"
              />
            } />
            <TooltipContent className="bg-background-tertiary text-foreground-muted text-xs border-border">
              {t("form.leadScoreTooltip")}
            </TooltipContent>
          </Tooltip>
        </div>
      </TooltipProvider>

      {/* Delivery chat_ids (D-08) */}
      <div className="flex flex-col gap-1">
        <label htmlFor="rule-chat-ids" className="text-xs font-semibold text-foreground-muted">
          {t("form.chatIdsLabel")}
        </label>
        <textarea
          id="rule-chat-ids"
          value={form.chatIds}
          onChange={(e) => setForm((p) => ({ ...p, chatIds: e.target.value }))}
          rows={3}
          placeholder="-1001234567890&#10;-1009876543210"
          className="rounded-md border border-border bg-background-tertiary px-3 py-2 text-sm text-foreground font-mono placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary resize-none"
        />
        <p className="text-xs text-foreground-subtle">
          {t("form.chatIdsHelp")}
        </p>
      </div>

      {/* Urgency channel */}
      <div className="flex flex-col gap-1">
        <label htmlFor="rule-channel" className="text-xs font-semibold text-foreground-muted">
          {t("form.urgencyChannelLabel")}
        </label>
        <select
          id="rule-channel"
          value={form.urgencyChannel}
          onChange={(e) => setForm((p) => ({ ...p, urgencyChannel: e.target.value as "dm" | "group" }))}
          className="rounded-md border border-border bg-background-tertiary px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary"
        >
          <option value="dm">{t("form.channelDm")}</option>
          <option value="group">{t("form.channelGroup")}</option>
        </select>
      </div>

      {/* Actions */}
      <div className="flex gap-3 justify-end pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary transition-colors"
        >
          {t("form.cancel")}
        </button>
        <button
          type="submit"
          disabled={isSaving}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background-secondary"
        >
          {isSaving ? t("form.saving") : t("form.save")}
        </button>
      </div>
    </form>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface RuleBuilderProps {
  isAdmin: boolean;
}

export function RuleBuilder({ isAdmin }: RuleBuilderProps) {
  const t = useTranslations("alerts");
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: rules = [], isLoading } = useQuery<AlertRuleOut[]>({
    queryKey: ["alert-rules"],
    queryFn: () => apiFetch<AlertRuleOut[]>("/alert-rules"),
  });

  const createMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch("/alert-rules", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
      setShowForm(false);
      setSaveError(null);
    },
    onError: () => {
      setSaveError(t("saveError"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/alert-rules/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-rules"] });
      setDeleteId(null);
    },
    onError: () => {
      setDeleteId(null);
    },
  });

  function handleSave(formState: RuleFormState) {
    // Build condition object from form state
    const condition: Record<string, unknown> = {};
    if (formState.kinds.length > 0) condition.kind = formState.kinds;
    if (formState.productId) condition.product_id = parseInt(formState.productId, 10);
    if (formState.volumeGte) condition.volume_gte = parseFloat(formState.volumeGte);
    if (formState.urgencies.length > 0) condition.urgency_in = formState.urgencies;
    if (formState.sourceKinds.length > 0) condition.source_kind = formState.sourceKinds;
    // lead_score_gte intentionally omitted — Phase 5 only (D-07)

    // Build channels from chat IDs
    const chatIds = formState.chatIds
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    const channels = chatIds.map((chatId) => ({
      type: formState.urgencyChannel === "dm" ? "telegram_dm" : "telegram_group",
      chat_id: parseInt(chatId, 10),
    }));

    createMutation.mutate({
      name: formState.name,
      condition,
      channels,
      is_enabled: true,
    });
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">{t("rulesTitle")}</h2>
        {isAdmin && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-dark transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background"
          >
            <Plus size={16} aria-hidden="true" />
            {t("createRule")}
          </button>
        )}
      </div>

      {/* Inline form */}
      {showForm && isAdmin && (
        <div className="rounded-lg border border-border bg-background-secondary p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4">{t("newRule")}</h3>
          {saveError && (
            <div className="mb-4 rounded-md border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
              {saveError}
            </div>
          )}
          <RuleForm
            onSave={handleSave}
            onCancel={() => { setShowForm(false); setSaveError(null); }}
            isSaving={createMutation.isPending}
          />
        </div>
      )}

      {/* Rules list */}
      {isLoading ? (
        <div className="flex flex-col gap-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg bg-background-tertiary animate-pulse" />
          ))}
        </div>
      ) : rules.length === 0 ? (
        <div className="rounded-lg border border-border bg-background-secondary p-6 text-center">
          <p className="text-sm text-foreground-muted">{t("emptyRules")}</p>
          {isAdmin && !showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="mt-2 text-sm text-accent hover:underline"
            >
              {t("createFirstRule")}
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="flex items-center justify-between rounded-lg border border-border bg-background-secondary px-4 py-3"
            >
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-sm font-medium text-foreground">{rule.name}</span>
                <PredicateSummary condition={rule.condition} />
                <span className="text-xs text-foreground-subtle">
                  {t("deliveryTargets", { count: rule.channels.length })}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ${
                    rule.is_enabled
                      ? "text-accent border border-accent/30"
                      : "text-foreground-muted border border-border"
                  }`}
                >
                  {rule.is_enabled ? t("statusActive") : t("statusPaused")}
                </span>
                {isAdmin && (
                  <button
                    onClick={() => setDeleteId(rule.id)}
                    className="rounded-md p-1.5 text-foreground-muted hover:text-urgency-high hover:bg-urgency-high/10 transition-colors"
                    aria-label={t("deleteRuleAria", { name: rule.name })}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete confirm */}
      <DeleteRuleDialog
        open={deleteId !== null}
        onConfirm={() => { if (deleteId !== null) deleteMutation.mutate(deleteId); }}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}

export type { RuleFormState };
