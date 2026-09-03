import { useEffect, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useAuthStore } from "@/entities/account";
import { useActiveCompany } from "@/entities/company";
import { ContractStatusBadge, contractApi, useContract } from "@/entities/contract";
import type { ContractDetail } from "@/entities/contract";
import { DIDOX_STATUS, didoxApi } from "@/entities/edi";
import { DidoxDocumentCard } from "@/features/didox-contract-document";
import { useDidoxSign } from "@/features/didox-sign";
import { EimzoSignButton } from "@/features/eimzo-sign";
import type { EimzoSigner } from "@/features/eimzo-sign";
import { ApiError } from "@/shared/api";
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
  PageHeader,
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
  const queryClient = useQueryClient();
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [printFormUrl, setPrintFormUrl] = useState<string | null>(null);
  const [printFormError, setPrintFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [reason, setReason] = useState("");

  const contract = query.data;
  // The Didox session belongs to the company the user is ACTING AS, and the
  // certificate is matched by its ИНН — so both come from the active company,
  // not from the contract (which carries names, not tax ids).
  // Hooks cannot sit behind the loading/error returns below.
  const active = useActiveCompany().activeCompany;
  const didoxSign = useDidoxSign(active?.id ?? 0, active?.tax_id ?? "");

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

  /**
   * The operator's print form. Re-fetched whenever the Didox status moves,
   * because the form CHANGES with it — a draft's carries no signature marks —
   * and an object URL is revoked on the way out so the blob is not leaked.
   */
  const didoxDocumentId = contract?.didox_document_id ?? null;
  const didoxStatus = contract?.didox_status ?? null;
  useEffect(() => {
    if (didoxDocumentId == null) return undefined;
    let url: string | null = null;
    let cancelled = false;
    setPrintFormError(null);
    void didoxApi
      .printForm(didoxDocumentId)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setPrintFormUrl(url);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPrintFormUrl(null);
          setPrintFormError(err instanceof ApiError ? (err.code ?? "failed") : "failed");
        }
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [didoxDocumentId, didoxStatus]);

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;
  if (query.isError || !contract) {
    return (
      <ErrorView title={t("errors.loadFailed")} retryLabel={t("common.retry")} onRetry={() => void query.refetch()}>
        <LinkButton to="/cabinet/contracts">{t("contracts.title")}</LinkButton>
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
      // The Didox prefill is derived from the contract's STATUS, so every action
      // here can change it — accepting the terms is what clears the `not_ready`
      // blocker. Without this the seller keeps reading «договор ещё не отправлен
      // на подпись» from cache and concludes the rail is stuck, until a reload.
      await queryClient.invalidateQueries({ queryKey: ["didox", "contract-prefill"] });
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
    verify: ({ pkcs7_64 }) =>
      contractApi.sign(id, pkcs7_64).then((c) => ({ ok: true, reason: null, data: c })),
  };

  const isDidoxRail = contract.signing_provider === "didox";
  /**
   * Whose turn it is, per DIDOX's status — not per our `signatures`, which stays
   * empty on this rail because we never hold the counterparty's PKCS#7.
   * `0` draft and `2` awaiting-us are ours to sign; `1` is theirs.
   */
  const didoxSignable =
    contract.didox_document_id != null &&
    (contract.didox_status === DIDOX_STATUS.draft ||
      contract.didox_status === DIDOX_STATUS.awaitingUs);

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

  /**
   * Who has signed, on the Didox rail — where `contract.signatures` is EMPTY by
   * design and asking it produces «ожидает подписи» about a party that signed
   * minutes ago. That is what it did to the seller here.
   *
   * `didox_status` arrives already restated for THIS viewer (the API mirrors
   * Didox's `1`/`2`, which are one state named from two ends), so it answers
   * both halves directly:
   *
   *   my side signed    ⟺ 1 (awaiting them) or 3 (both)
   *   their side signed ⟺ 2 (awaiting me)   or 3 (both)
   *
   * `null` means "we cannot tell" — a rail with no document yet — and is not the
   * same as "has not signed".
   */
  const didoxSignedFor = (companyId: number): boolean | null => {
    if (!isDidoxRail || contract.didox_document_id == null) return null;
    const status = contract.didox_status;
    if (status == null) return null;
    const mine = companyId === myCompanyId;
    const bothSigned = status === DIDOX_STATUS.signed;
    if (bothSigned) return true;
    return mine ? status === DIDOX_STATUS.awaitingPartner : status === DIDOX_STATUS.awaitingUs;
  };

  const partySteps: StatusStep[] = [
    { id: "initiator", companyId: contract.initiator_company_id, name: contract.initiator_name },
    {
      id: "counterparty",
      companyId: contract.counterparty_company_id,
      name: contract.counterparty_name,
    },
  ].map(({ id, companyId, name }) => {
    const at = signedAtFor(companyId);
    const viaDidox = didoxSignedFor(companyId);
    const signed = at != null || viaDidox === true;
    const company = name ?? `#${companyId}`;
    return {
      id: `signed-${id}`,
      // Wording follows the state — an unsigned step must not read "signed by".
      label: signed
        ? t("contracts.timeline.signedBy", { company })
        : t("contracts.timeline.awaitingSignature", { company }),
      // Didox tells us THAT a side signed, never WHEN. Borrowing the contract's
      // «signed at» phrasing here would invent a moment we do not have.
      hint: at
        ? formatDateTime(at, lang)
        : signed
          ? t("contracts.timeline.signedNoDate")
          : t("contracts.timeline.awaiting"),
      // Only meaningful to "await" a signature once the contract is out for signing.
      state: signed ? "done" : contract.status === "pending_signatures" ? "current" : "pending",
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
      <PageHeader
        backTo="/cabinet/contracts"
        backLabel={t("contracts.title")}
        title={contract.title}
        subtitle={`${contract.initiator_name} → ${contract.counterparty_name}`}
        badge={<ContractStatusBadge status={contract.status} />}
      />

      {/* On the Didox rail the document has to EXIST before anyone can sign it,
          and creating it is the seller's move. The card removes itself once the
          document is there and the signing controls below take over. */}
      {isDidoxRail && contract.didox_document_id == null && active ? (
        <DidoxDocumentCard
          companyId={active.id}
          contractId={id}
          onCreated={() => void query.refetch()}
        />
      ) : null}

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
          {/* The two rails sign different things. On `eimzo` we verify the PKCS#7
              ourselves against a challenge; on `didox` the document lives at the
              operator, so it is a two-round-trip exchange and `iSigned` cannot be
              derived from `signatures` — Didox's own status is the truth. */}
          {contract.status === "pending_signatures" && isDidoxRail ? (
            <>
              {didoxSignable ? (
                <Button
                  disabled={didoxSign.signing}
                  onClick={() =>
                    void didoxSign
                      .sign(contract.didox_document_id!)
                      .then(() => query.refetch())
                  }
                  data-testid="contract-sign-didox"
                >
                  {didoxSign.signing
                    ? t("didox.signing")
                    : /* NOT `contracts.actions.sign` — that reads «Подписать через
                         E-IMZO», which is the OTHER rail. The key is the same here,
                         but the document goes to the operator and to my.soliq.uz,
                         and a signatory has to be able to tell which one they are
                         signing. */
                      t("didox.signAndSend")}
                </Button>
              ) : (
                <span className="text-sm text-text-muted" data-testid="didox-awaiting">
                  {t(`didox.documentStatus.${contract.didox_status ?? 0}`, {
                    defaultValue: t("contracts.awaitingOther"),
                  })}
                </span>
              )}
              {didoxSign.error && (
                <span className="text-sm text-danger" data-testid="didox-sign-error">
                  {/* A provider refusal is rendered WITH their sentence — it names
                      the field and the company, which no generic string can. */}
                  {t(`didox.signErrors.${didoxSign.error}`, {
                    message: didoxSign.errorMessage ?? "",
                  })}
                </span>
              )}
            </>
          ) : null}
          {contract.status === "pending_signatures" && !isDidoxRail && !iSigned ? (
            <EimzoSignButton
              signer={signer}
              variant="primary"
              label={t("contracts.actions.sign")}
              onConfirmed={() => void query.refetch()}
            />
          ) : null}
          {contract.status === "pending_signatures" && !isDidoxRail && iSigned ? (
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

      {/* The operator's own rendering, once a document exists at Didox. A
          different artefact from ours above: it carries their electronic-document
          id and the marks of both signatures, and it is what my.soliq.uz shows.
          Nothing is offered for download — the archive is kept as evidence and
          there is nobody asking to fetch it. */}
      {isDidoxRail && contract.didox_document_id != null ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("didox.printForm.title")}</CardTitle>
          </CardHeader>
          <CardBody>
            {printFormUrl ? (
              <iframe
                src={printFormUrl}
                title={t("didox.printForm.title")}
                className="h-[600px] w-full rounded-md border border-border"
                data-testid="didox-print-form"
              />
            ) : (
              <p className="text-sm text-text-muted" data-testid="didox-print-form-state">
                {printFormError
                  ? t(`didox.printForm.errors.${printFormError}`, {
                      defaultValue: t("didox.printForm.errors.failed"),
                    })
                  : t("didox.printForm.loading")}
              </p>
            )}
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
