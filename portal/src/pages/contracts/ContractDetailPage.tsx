import { useEffect, useState } from "react";

import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { ContractStatusBadge, contractApi, useContract } from "@/entities/contract";
import type { ContractDetail } from "@/entities/contract";
import { EimzoSignButton } from "@/features/eimzo-sign";
import type { EimzoSigner } from "@/features/eimzo-sign";
import { coerceLang } from "@/shared/i18n";
import { formatDateTime } from "@/shared/lib";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  ErrorView,
  LinkButton,
  LoadingView,
  StatusStepper,
  Textarea,
} from "@/shared/ui";
import type { StatusStep } from "@/shared/ui";

export function ContractDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ contractId: string }>();
  const id = Number(params.contractId);
  const lang = coerceLang(useAuthStore((s) => s.account?.language));
  const query = useContract(Number.isInteger(id) ? id : null);
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [reason, setReason] = useState("");

  const contract = query.data;

  useEffect(() => {
    let cancelled = false;
    if (contract?.document_available) {
      void contractApi.documentUrl(id).then((url) => {
        if (!cancelled) setDocUrl(url);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [contract?.document_available, contract?.document_sha256, id]);

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;
  if (query.isError || !contract) {
    return (
      <ErrorView title={t("errors.loadFailed")} retryLabel={t("common.retry")} onRetry={() => void query.refetch()}>
        <LinkButton to="/contracts">{t("contracts.title")}</LinkButton>
      </ErrorView>
    );
  }

  const myCompanyId =
    contract.role === "initiator" ? contract.initiator_company_id : contract.counterparty_company_id;
  const iSigned = contract.signatures.some((s) => s.company_id === myCompanyId);

  async function act(fn: () => Promise<ContractDetail>): Promise<void> {
    setBusy(true);
    try {
      await fn();
      await query.refetch();
    } finally {
      setBusy(false);
      setDeclineOpen(false);
    }
  }

  async function openPdf(): Promise<void> {
    window.open(await contractApi.documentUrl(id), "_blank", "noopener");
  }

  async function downloadBundle(): Promise<void> {
    const blob = await contractApi.bundleBlob(id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `contract_${contract?.public_id ?? id}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const signer: EimzoSigner<ContractDetail> = {
    getChallenge: () => contractApi.signChallenge(id).then((r) => r.challenge),
    verify: (pkcs7) => contractApi.sign(id, pkcs7).then((c) => ({ ok: true, reason: null, data: c })),
  };

  const isInitiator = contract.role === "initiator";
  const isCounterparty = contract.role === "counterparty";

  /**
   * The signing process as a timeline: draft → sent → each party's signature →
   * active. Derived purely from the timestamps the API already returns, so a step
   * is `done` once its timestamp exists, `current` for the one being waited on,
   * and `pending` beyond that.
   */
  const signedAtFor = (companyId: number): string | null =>
    contract.signatures.find((s) => s.company_id === companyId)?.signed_at ?? null;

  const partySteps: StatusStep[] = [
    { id: "initiator", companyId: contract.initiator_company_id, name: contract.initiator_name },
    {
      id: "counterparty",
      companyId: contract.counterparty_company_id,
      name: contract.counterparty_name,
    },
  ].map(({ id, companyId, name }) => {
    const at = signedAtFor(companyId);
    const company = name ?? `#${companyId}`;
    return {
      id: `signed-${id}`,
      // Wording follows the state — an unsigned step must not read "signed by".
      label: at
        ? t("contracts.timeline.signedBy", { company })
        : t("contracts.timeline.awaitingSignature", { company }),
      hint: at ? formatDateTime(at, lang) : t("contracts.timeline.awaiting"),
      // Only meaningful to "await" a signature once the contract is out for signing.
      state: at ? "done" : contract.status === "pending_signatures" ? "current" : "pending",
    };
  });

  const signingSteps: StatusStep[] = [
    {
      id: "created",
      label: t("contracts.timeline.created"),
      hint: formatDateTime(contract.created_at, lang),
      state: "done",
    },
    {
      id: "sent",
      label: t("contracts.timeline.sent"),
      hint: contract.sent_at
        ? formatDateTime(contract.sent_at, lang)
        : t("contracts.timeline.awaiting"),
      state: contract.sent_at ? "done" : "current",
    },
    ...partySteps,
    {
      id: "active",
      label: t("contracts.timeline.active"),
      hint: contract.activated_at
        ? formatDateTime(contract.activated_at, lang)
        : t("contracts.timeline.awaiting"),
      state: contract.activated_at ? "done" : "pending",
    },
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text">{contract.title}</h1>
          <p className="mt-1 text-sm text-text-muted">
            {contract.initiator_name} → {contract.counterparty_name}
          </p>
        </div>
        <ContractStatusBadge status={contract.status} />
      </div>

      {/* Action bar */}
      <Card>
        <CardBody className="flex flex-wrap gap-3" data-testid="contract-actions">
          {contract.status === "draft" && isInitiator ? (
            <Button disabled={busy} onClick={() => void act(() => contractApi.send(id))} data-testid="contract-send">
              {t("contracts.actions.send")}
            </Button>
          ) : null}
          {contract.status === "pending_counterparty" && isCounterparty ? (
            <>
              <Button disabled={busy} onClick={() => void act(() => contractApi.accept(id))} data-testid="contract-accept">
                {t("contracts.actions.accept")}
              </Button>
              <Button variant="danger" disabled={busy} onClick={() => setDeclineOpen((v) => !v)}>
                {t("contracts.actions.decline")}
              </Button>
            </>
          ) : null}
          {contract.status === "pending_signatures" && !iSigned ? (
            <EimzoSignButton
              signer={signer}
              variant="primary"
              label={t("contracts.actions.sign")}
              onConfirmed={() => void query.refetch()}
            />
          ) : null}
          {contract.status === "pending_signatures" && iSigned ? (
            <span className="text-sm text-text-muted">{t("contracts.awaitingOther")}</span>
          ) : null}
          {(contract.status === "draft" ||
            contract.status === "pending_counterparty" ||
            contract.status === "pending_signatures") &&
          isInitiator &&
          contract.signatures.length === 0 ? (
            <Button variant="ghost" disabled={busy} onClick={() => void act(() => contractApi.cancel(id))}>
              {t("contracts.actions.cancel")}
            </Button>
          ) : null}
          {contract.status === "active" ? (
            <>
              <Button onClick={() => void openPdf()} data-testid="contract-download">
                {t("contracts.actions.downloadPdf")}
              </Button>
              <Button variant="secondary" onClick={() => void downloadBundle()}>
                {t("contracts.actions.downloadBundle")}
              </Button>
            </>
          ) : null}
        </CardBody>
      </Card>

      {declineOpen ? (
        <Card>
          <CardBody className="space-y-3">
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("contracts.declineReason")}
              rows={3}
            />
            <Button
              variant="danger"
              disabled={busy || !reason.trim()}
              onClick={() => void act(() => contractApi.decline(id, reason.trim()))}
            >
              {t("contracts.actions.confirmDecline")}
            </Button>
          </CardBody>
        </Card>
      ) : null}

      {contract.declined_reason ? (
        <Alert tone="danger" title={t("contracts.declinedTitle")}>
          {contract.declined_reason}
        </Alert>
      ) : null}

      {/* Document preview */}
      {docUrl ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("contracts.document")}</CardTitle>
          </CardHeader>
          <CardBody>
            <iframe
              src={docUrl}
              title={t("contracts.document")}
              className="h-[600px] w-full rounded-md border border-border"
              data-testid="contract-pdf"
            />
          </CardBody>
        </Card>
      ) : null}

      {/* Signing timeline (mockup sheet 7) — same data as the old flat list,
          read as the progress of the signing process. */}
      <Card>
        <CardHeader>
          <CardTitle>{t("contracts.signatures")}</CardTitle>
        </CardHeader>
        <CardBody>
          <StatusStepper steps={signingSteps} />
        </CardBody>
      </Card>
    </div>
  );
}
