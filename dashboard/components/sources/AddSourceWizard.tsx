"use client";

/**
 * AddSourceWizard — 4-step wizard for adding a new data source.
 *
 * Step 1: Pick type (HTML Table, RSS Feed, Telegram Channel [Phase 5], LLM Page [Phase 5])
 * Step 2: Configure (auto-form from GET /admin/source-types config_schema → JsonSchemaForm)
 * Step 3: Test (html_table/rss only) — POST /sources → POST /sources/{id}/test
 *          telegram_channel/llm_page skip test and save as pending
 * Step 4: Enable / Save as Pending
 *
 * D-04/D-05/D-06 contracts. No hardcoded hex.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Globe, Rss, MessageSquare, FileText, CheckCircle, XCircle, ChevronRight } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { JsonSchemaForm, type JsonSchemaFormValues } from "./JsonSchemaForm";

// ─── Types ─────────────────────────────────────────────────────────────────────

interface SourceTypeItem {
  type_name: string;
  display_name?: string;
  description?: string;
  no_code: boolean;
  config_schema: Record<string, unknown>;
}

interface SourceTestResult {
  ok: boolean;
  sample_rows: Array<Record<string, unknown>>;
  error: string | null;
}

type WizardStep = 1 | 2 | 3 | 4;

// Adapter types that are pending (Phase 5)
const PENDING_ADAPTERS = new Set(["telegram_channel", "llm_page"]);

const TYPE_LABELS: Record<string, string> = {
  html_table: "HTML Table",
  rss: "RSS Feed",
  telegram_channel: "Telegram Channel",
  llm_page: "LLM Page",
};

const TYPE_DESCRIPTIONS: Record<string, string> = {
  html_table: "Fetch data from an HTML table on a public web page",
  rss: "Subscribe to an RSS or Atom feed",
  telegram_channel: "Monitor a public Telegram channel",
  llm_page: "Extract structured data from a web page using AI",
};

// ─── Step indicator ───────────────────────────────────────────────────────────

function StepIndicator({ current, total }: { current: WizardStep; total: number }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {Array.from({ length: total }, (_, i) => {
        const step = (i + 1) as WizardStep;
        const isDone = step < current;
        const isActive = step === current;
        return (
          <div key={step} className="flex items-center gap-2">
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
                isDone
                  ? "bg-accent text-white"
                  : isActive
                    ? "bg-accent text-white ring-2 ring-accent ring-offset-2 ring-offset-background-secondary"
                    : "bg-background-tertiary text-foreground-muted"
              }`}
            >
              {isDone ? <CheckCircle size={14} /> : step}
            </div>
            {i < total - 1 && (
              <div className={`w-8 h-0.5 ${step < current ? "bg-accent" : "bg-border"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Step 1: Pick type ────────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, React.ReactNode> = {
  html_table: <Globe size={32} className="text-foreground-muted" />,
  rss: <Rss size={32} className="text-foreground-muted" />,
  telegram_channel: <MessageSquare size={32} className="text-foreground-muted" />,
  llm_page: <FileText size={32} className="text-foreground-muted" />,
};

function Step1PickType({
  sourceTypes,
  selected,
  onSelect,
  onNext,
}: {
  sourceTypes: SourceTypeItem[];
  selected: string | null;
  onSelect: (type: string) => void;
  onNext: () => void;
}) {
  const [pendingWarning, setPendingWarning] = useState<string | null>(null);

  function handleSelect(typeName: string) {
    onSelect(typeName);
    if (PENDING_ADAPTERS.has(typeName)) {
      setPendingWarning(typeName);
    } else {
      setPendingWarning(null);
    }
  }

  const noCodeTypes = sourceTypes.filter((t) => t.no_code);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        {noCodeTypes.map((sourceType) => {
          const isPending = PENDING_ADAPTERS.has(sourceType.type_name);
          const isSelected = selected === sourceType.type_name;
          const label = TYPE_LABELS[sourceType.type_name] ?? sourceType.type_name;
          const description = TYPE_DESCRIPTIONS[sourceType.type_name] ?? "";

          return (
            <button
              key={sourceType.type_name}
              type="button"
              onClick={() => handleSelect(sourceType.type_name)}
              className={`relative flex flex-col items-center gap-2 rounded-lg border p-4 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-background-secondary ${
                isSelected
                  ? "border-accent bg-accent/10"
                  : "border-border bg-background-tertiary hover:border-accent/50"
              }`}
              style={{ minHeight: "100px" }}
            >
              {isPending && (
                <span className="absolute top-2 right-2 rounded px-1.5 py-0.5 text-xs font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30">
                  Phase 5
                </span>
              )}
              {TYPE_ICONS[sourceType.type_name] ?? <Globe size={32} className="text-foreground-muted" />}
              <div className="w-full text-center">
                <div className="text-sm font-medium text-foreground">{label}</div>
                <div className="text-xs text-foreground-muted mt-0.5">{description}</div>
              </div>
            </button>
          );
        })}
      </div>

      {pendingWarning && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
          <strong>{TYPE_LABELS[pendingWarning]}</strong> requires Phase 5 features. You can save
          the configuration now as pending — it will activate when Phase 5 is available.
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onNext}
          disabled={!selected}
          className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Continue <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

// ─── Preview table (Step 3) ───────────────────────────────────────────────────

const PREVIEW_COLUMNS = ["product", "grade", "volume", "price", "currency", "section", "event_at"] as const;

function PreviewTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead className="bg-background-tertiary">
          <tr>
            {PREVIEW_COLUMNS.map((col) => (
              <th key={col} className="px-3 py-2 text-left font-semibold text-foreground-muted capitalize">
                {col.replace("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? "bg-background-secondary" : "bg-background"}>
              {PREVIEW_COLUMNS.map((col) => (
                <td key={col} className="px-3 py-2 text-foreground font-mono">
                  {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-foreground-subtle">—</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Main wizard component ────────────────────────────────────────────────────

interface AddSourceWizardProps {
  open: boolean;
  onClose: () => void;
}

export function AddSourceWizard({ open, onClose }: AddSourceWizardProps) {
  const queryClient = useQueryClient();

  const [step, setStep] = useState<WizardStep>(1);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [sourceName, setSourceName] = useState("");
  const [createdSourceId, setCreatedSourceId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<SourceTestResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [isEnabling, setIsEnabling] = useState(false);
  const [finalError, setFinalError] = useState<string | null>(null);

  // Fetch available source types
  const { data: sourceTypes = [] } = useQuery<SourceTypeItem[]>({
    queryKey: ["source-types"],
    queryFn: () => apiFetch<SourceTypeItem[]>("/admin/source-types"),
    enabled: open,
  });

  const isPendingType = selectedType ? PENDING_ADAPTERS.has(selectedType) : false;

  const selectedSchemaType = sourceTypes.find((t) => t.type_name === selectedType);

  // Create source mutation
  const createSource = useMutation({
    mutationFn: (body: { adapter: string; name: string; config: Record<string, unknown> }) =>
      apiFetch<{ id: number }>("/sources", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });

  function handleClose() {
    // Reset state
    setStep(1);
    setSelectedType(null);
    setSourceName("");
    setCreatedSourceId(null);
    setTestResult(null);
    setIsTesting(false);
    setTestError(null);
    setIsEnabling(false);
    setFinalError(null);
    onClose();
  }

  async function handleConfigSubmit(values: JsonSchemaFormValues) {
    if (!selectedType || !sourceName.trim()) return;

    try {
      const result = await createSource.mutateAsync({
        adapter: selectedType,
        name: sourceName.trim(),
        config: values as Record<string, unknown>,
      });
      setCreatedSourceId(result.id);
      setStep(3);
    } catch {
      // Error handled by createSource.error
    }
  }

  async function handleRunTest() {
    if (!createdSourceId) return;
    setIsTesting(true);
    setTestError(null);
    setTestResult(null);

    try {
      const result = await apiFetch<SourceTestResult>(`/sources/${createdSourceId}/test`, {
        method: "POST",
      });
      setTestResult(result);
      if (result.ok) {
        // Test passed — advance to step 4
        setStep(4);
      }
    } catch {
      setTestError("Could not run test. Check your connection and try again.");
    } finally {
      setIsTesting(false);
    }
  }

  async function handleEnable() {
    if (!createdSourceId) return;
    setIsEnabling(true);
    setFinalError(null);
    try {
      await apiFetch(`/sources/${createdSourceId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_enabled: true }),
      });
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      handleClose();
    } catch {
      setFinalError("Failed to enable source. Verify the test passed and try again.");
      setIsEnabling(false);
    }
  }

  async function handleSaveAsPending() {
    // Source was already created (is_enabled=false by default)
    queryClient.invalidateQueries({ queryKey: ["sources"] });
    handleClose();
  }

  const stepLabels = ["Pick Type", "Configure", "Test", "Enable"];

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
      <DialogContent className="max-w-[560px] bg-background-secondary rounded-xl shadow-2xl border-border">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold text-foreground">
            Add Data Source
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          <StepIndicator current={step} total={4} />

          <div className="text-sm font-semibold text-foreground-muted uppercase tracking-wider text-xs">
            Step {step}: {stepLabels[step - 1]}
          </div>

          {/* Step 1: Pick type */}
          {step === 1 && (
            <Step1PickType
              sourceTypes={sourceTypes}
              selected={selectedType}
              onSelect={setSelectedType}
              onNext={() => { if (selectedType) setStep(2); }}
            />
          )}

          {/* Step 2: Configure */}
          {step === 2 && selectedSchemaType && (
            <div className="flex flex-col gap-4">
              {/* Source name */}
              <div className="flex flex-col gap-1">
                <label htmlFor="source-name" className="text-xs font-semibold text-foreground-muted">
                  Source Name <span className="text-urgency-high">*</span>
                </label>
                <input
                  id="source-name"
                  type="text"
                  value={sourceName}
                  onChange={(e) => setSourceName(e.target.value)}
                  placeholder={`My ${TYPE_LABELS[selectedType!] ?? selectedType} source`}
                  className="rounded-md border border-border bg-background-tertiary px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1 focus:ring-offset-background-secondary"
                />
              </div>

              {isPendingType && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
                  This source type is available in Phase 5. Your configuration will be saved
                  but the source will remain in pending state until then.
                </div>
              )}

              <JsonSchemaForm
                schema={selectedSchemaType.config_schema as Parameters<typeof JsonSchemaForm>[0]["schema"]}
                onSubmit={async (values) => {
                  if (!sourceName.trim()) {
                    alert("Please enter a source name.");
                    return;
                  }
                  if (isPendingType) {
                    // Pending types: create and save directly (no test step)
                    try {
                      const result = await createSource.mutateAsync({
                        adapter: selectedType!,
                        name: sourceName.trim(),
                        config: values as Record<string, unknown>,
                      });
                      setCreatedSourceId(result.id);
                      setStep(4); // jump to step 4 (Save as Pending)
                    } catch {
                      // error shown below
                    }
                  } else {
                    await handleConfigSubmit(values);
                  }
                }}
                onBack={() => setStep(1)}
                submitLabel={isPendingType ? "Save Configuration" : "Continue to Test"}
              />

              {createSource.error && (
                <div className="rounded-md border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
                  Failed to save configuration. Please try again.
                </div>
              )}
            </div>
          )}

          {/* Step 3: Test */}
          {step === 3 && (
            <div className="flex flex-col gap-4">
              {!testResult && !isTesting && (
                <div className="text-sm text-foreground-muted">
                  Run a live test to verify the source extracts data correctly.
                  Up to 10 normalized preview rows will be shown.
                </div>
              )}

              {isTesting && (
                <div className="flex items-center gap-3 text-sm text-foreground-muted py-4">
                  <div className="h-4 w-4 rounded-full border-2 border-accent border-t-transparent animate-spin" />
                  Fetching source…
                </div>
              )}

              {testError && (
                <div className="flex flex-col gap-2 rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-urgency-high">
                    <XCircle size={16} /> Test failed
                  </div>
                  <p className="text-sm text-foreground-muted">
                    Could not extract data from this source. Check the URL and selectors, then try again.
                  </p>
                </div>
              )}

              {testResult && !testResult.ok && (
                <div className="flex flex-col gap-2 rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-urgency-high">
                    <XCircle size={16} /> Test failed
                  </div>
                  <p className="text-sm text-foreground-muted">
                    {testResult.error ?? "Could not extract data from this source. Check the URL and selectors, then try again."}
                  </p>
                </div>
              )}

              {testResult && testResult.ok && (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-accent">
                    <CheckCircle size={16} /> Test passed
                  </div>
                  <p className="text-sm text-foreground-muted">
                    {testResult.sample_rows.length} records extracted. Review the preview and enable the source.
                  </p>
                  <PreviewTable rows={testResult.sample_rows} />
                </div>
              )}

              <div className="flex gap-3 justify-between">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="rounded-md border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary transition-colors"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={handleRunTest}
                  disabled={isTesting}
                  className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50 transition-colors"
                >
                  {isTesting ? (
                    <>
                      <div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      Running…
                    </>
                  ) : (
                    "Run Test"
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Enable / Save as Pending */}
          {step === 4 && (
            <div className="flex flex-col gap-4">
              {isPendingType ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
                  <p className="text-sm text-amber-400 font-semibold mb-1">
                    Configuration saved — Pending activation (Phase 5)
                  </p>
                  <p className="text-sm text-foreground-muted">
                    This source has been saved. It will activate automatically when Phase 5
                    features are available.
                  </p>
                </div>
              ) : (
                <div className="rounded-lg border border-accent/30 bg-accent/10 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-accent mb-1">
                    <CheckCircle size={16} /> Test passed — source is ready to enable
                  </div>
                  <p className="text-sm text-foreground-muted">
                    Enable the source to begin collecting data from it.
                  </p>
                </div>
              )}

              {finalError && (
                <div className="rounded-md border border-urgency-high/30 bg-urgency-high/10 p-3 text-sm text-urgency-high">
                  {finalError}
                </div>
              )}

              <div className="flex flex-col gap-2">
                {!isPendingType && (
                  <button
                    type="button"
                    onClick={handleEnable}
                    disabled={isEnabling}
                    className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50 transition-colors"
                  >
                    {isEnabling ? "Enabling…" : "Enable Source"}
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleSaveAsPending}
                  className="w-full rounded-md border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary transition-colors"
                >
                  {isPendingType ? "Done" : "Save as Pending"}
                </button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
