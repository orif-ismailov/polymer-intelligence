import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";

import { useActiveCompany } from "@/entities/company";
import {
  presetFieldsOf,
  useContractTemplates,
  useTermPresets,
} from "@/entities/contract";
import type { TermPreset } from "@/entities/contract";
import {
  TermPresetDialog,
  useArchiveTermPreset,
} from "@/features/contract-term-preset";
import {
  Button,
  Card,
  CardBody,
  ContractSheetIcon,
  EmptyState,
  ErrorView,
  LoadingView,
  PageHeader,
} from "@/shared/ui";

/**
 * «Шаблоны условий» — the company's saved contract terms.
 *
 * Every company has its own payment and delivery terms; saving them here means
 * choosing one on the contract form instead of typing them again. Owners and
 * managers edit, every member reads (and uses them).
 */
export function ContractTermsPage() {
  const { t } = useTranslation();
  const active = useActiveCompany().activeCompany;
  const companyId = active?.id ?? null;
  const templates = useContractTemplates();
  const presets = useTermPresets(companyId);
  const archive = useArchiveTermPreset(companyId ?? 0);
  const [editing, setEditing] = useState<TermPreset | null>(null);
  const [open, setOpen] = useState(false);

  const fields = useMemo(
    () => presetFieldsOf(templates.data ?? []),
    [templates.data],
  );
  const titles = useMemo(
    () => new Map(fields.map((f) => [f.key, f.title])),
    [fields],
  );
  const canEdit = presets.data?.can_edit ?? false;

  function openEditor(preset: TermPreset | null): void {
    setEditing(preset);
    setOpen(true);
  }

  if (presets.isLoading || templates.isLoading)
    return <LoadingView label={t("common.loading")} />;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        backTo="/cabinet/contracts"
        backLabel={t("contracts.title")}
        title={t("contractTerms.title")}
        subtitle={t("contractTerms.subtitle")}
        actions={
          canEdit ? (
            <Button
              onClick={() => openEditor(null)}
              data-testid="term-preset-new"
            >
              {t("contractTerms.new")}
            </Button>
          ) : null
        }
      />

      {presets.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void presets.refetch()}
        />
      ) : null}

      {presets.data && presets.data.items.length === 0 ? (
        <EmptyState
          icon={<ContractSheetIcon size={28} />}
          title={t("contractTerms.empty")}
          description={
            canEdit ? t("contractTerms.emptyBody") : t("contractTerms.readOnly")
          }
        />
      ) : null}

      <div className="space-y-3">
        {(presets.data?.items ?? []).map((preset) => (
          <Card key={preset.id}>
            <CardBody className="space-y-3" data-testid="term-preset-row">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-base font-semibold text-text">
                  {preset.name}
                </h2>
                {canEdit ? (
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => openEditor(preset)}
                    >
                      {t("common.edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={archive.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            t("contractTerms.archiveConfirm", {
                              name: preset.name,
                            }),
                          )
                        )
                          archive.mutate(preset.id);
                      }}
                      data-testid="term-preset-archive"
                    >
                      {t("common.archive")}
                    </Button>
                  </div>
                ) : null}
              </div>
              <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                {Object.entries(preset.terms).map(([key, value]) => (
                  <div key={key} className="min-w-0">
                    <dt className="text-text-muted">
                      {titles.get(key) ?? key}
                    </dt>
                    <dd className="break-words text-text">{value}</dd>
                  </div>
                ))}
              </dl>
            </CardBody>
          </Card>
        ))}
      </div>

      {companyId != null ? (
        <TermPresetDialog
          open={open}
          onClose={() => setOpen(false)}
          companyId={companyId}
          fields={fields}
          preset={editing}
        />
      ) : null}
    </div>
  );
}
