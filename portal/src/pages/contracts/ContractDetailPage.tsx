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
  Textarea,
} from "@/shared/ui";

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

  async function openUrl(getter: () => Promise<string>): Promise<void> {
    const url = await getter();
    window.open(url, "_blank", "noopener");
  }

  const signer: EimzoSigner<ContractDetail> = {
    getChallenge: () => contractApi.signChallenge(id).then((r) => r.challenge),
    verify: (pkcs7) => contractApi.sign(id, pkcs7).then((c) => ({ ok: true, reason: null, data: c })),
  };

  const isInitiator = contract.role === "initiator";
  const isCounterparty = contract.role === "counterparty";

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
              <Button onClick={() => void openUrl(() => contractApi.documentUrl(id))} data-testid="contract-download">
                {t("contracts.actions.downloadPdf")}
              </Button>
              <Button variant="secondary" onClick={() => void openUrl(() => contractApi.bundleUrl(id))}>
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

      {/* Signatures + timeline */}
      <Card>
        <CardHeader>
          <CardTitle>{t("contracts.signatures")}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          {contract.signatures.length === 0 ? (
            <p className="text-sm text-text-muted">{t("contracts.noSignatures")}</p>
          ) : (
            <ul className="space-y-2">
              {contract.signatures.map((s) => (
                <li key={s.company_id} className="flex items-center justify-between text-sm">
                  <span className="text-text">{s.company_name}</span>
                  <span className="text-text-muted">{formatDateTime(s.signed_at, lang)}</span>
                </li>
              ))}
            </ul>
          )}
          <dl className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-sm">
            <div>
              <dt className="text-text-muted">{t("contracts.createdAt")}</dt>
              <dd className="text-text">{formatDateTime(contract.created_at, lang)}</dd>
            </div>
            {contract.sent_at ? (
              <div>
                <dt className="text-text-muted">{t("contracts.sentAt")}</dt>
                <dd className="text-text">{formatDateTime(contract.sent_at, lang)}</dd>
              </div>
            ) : null}
            {contract.activated_at ? (
              <div>
                <dt className="text-text-muted">{t("contracts.activatedAt")}</dt>
                <dd className="text-text">{formatDateTime(contract.activated_at, lang)}</dd>
              </div>
            ) : null}
          </dl>
        </CardBody>
      </Card>
    </div>
  );
}
