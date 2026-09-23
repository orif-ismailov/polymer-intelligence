import { useState } from "react";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { didoxApi } from "@/entities/edi";
import type { DidoxIkpuChoice } from "@/entities/edi";
import { useDidoxSession } from "@/features/didox-session";
import { IkpuPicker } from "@/features/ikpu-picker";
import type { IkpuValue } from "@/features/ikpu-picker";
import { ApiError } from "@/shared/api";
import { Alert, Button } from "@/shared/ui";

interface DidoxDocumentCardProps {
  companyId: number;
  /** The acting company's ИНН — the ИКПУ picker opens a Didox session with it. */
  taxId: string;
  contractId: number;
  onCreated: () => void;
}

/**
 * The step that puts a contract in front of the tax authority (P7.a).
 *
 * On the Didox rail the parties do not sign a PDF we hold — they sign a document
 * the EDI operator holds, and that document has to be created first. Until it
 * exists there is nothing to sign, which is why this card sits where the sign
 * button will later appear.
 *
 * **The seller creates it.** The ЭСФ that follows is issued by the seller and
 * quotes this document's number, so the buyer sees the state and waits.
 *
 * Blockers arrive as a list rather than one at a time: a seller who discovers
 * three missing things in three round trips — each after loading an E-IMZO key —
 * concludes the feature is broken.
 *
 * **A contract from a tender has no offer**, and the offer was the only place a
 * document line got its ИКПУ — so the seller picks it here, with the same picker
 * the offer form uses. Each pick re-reads the prefill with that code, which is
 * how «the buyer has not declared this code» shows up before the key password
 * rather than as Didox's refusal after it.
 */
export function DidoxDocumentCard({
  companyId,
  taxId,
  contractId,
  onCreated,
}: DidoxDocumentCardProps) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ikpu, setIkpu] = useState<IkpuValue | null>(null);
  const session = useDidoxSession(companyId, taxId);
  const ikpuCode = ikpu?.code;

  const prefill = useQuery({
    queryKey: ["didox", "contract-prefill", companyId, contractId, ikpuCode ?? null],
    queryFn: () => didoxApi.contractPrefill(companyId, contractId, ikpuCode),
    // A new pick re-checks the buyer's list; the card must not vanish meanwhile.
    placeholderData: keepPreviousData,
  });

  if (prefill.isLoading || !prefill.data) return null;
  const data = prefill.data;

  // Already at the operator: the signing controls take over from here.
  if (data.document_id != null) return null;

  const isSeller = companyId === data.seller_company_id;
  const blocking = data.blockers.filter((code) => code !== "not_seller");
  // Complete or nothing: the code, its package and the origin all reach soliq.
  const choice: DidoxIkpuChoice | null =
    ikpu && ikpu.packageCode && ikpu.origin != null
      ? {
          code: ikpu.code,
          name: ikpu.name,
          package_code: ikpu.packageCode,
          package_name: ikpu.packageName,
          origin: ikpu.origin,
        }
      : null;
  const needsChoice = data.ikpu_choice && isSeller;
  const canCreate = blocking.length === 0 && (!needsChoice || choice != null) && !prefill.isFetching;

  async function create(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await didoxApi.createContractDocument(companyId, contractId, [], needsChoice ? choice : null);
      onCreated();
    } catch (err) {
      // Every refusal is a named condition the seller can act on — a bare
      // "что-то пошло не так" would leave them pressing the same button.
      setError(err instanceof ApiError ? (err.code ?? "failed") : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-border p-4" data-testid="didox-doc-card">
      <div>
        <h3 className="text-base font-medium text-text">{t("didoxDocument.title")}</h3>
        <p className="mt-1 text-sm text-text-muted">
          {isSeller ? t("didoxDocument.sellerHint") : t("didoxDocument.buyerHint")}
        </p>
      </div>

      {data.lines.length > 0 && (
        <ul className="space-y-1 text-sm" data-testid="didox-doc-lines">
          {data.lines.map((line) => (
            <li key={line.name} className="flex justify-between gap-3">
              <span className="truncate">{line.name}</span>
              <span className="num shrink-0 text-text-muted">
                {line.count} × {line.price}
              </span>
            </li>
          ))}
        </ul>
      )}

      {needsChoice && (
        <div className="space-y-2 rounded-md border border-border p-3" data-testid="didox-doc-ikpu">
          <div>
            <p className="text-sm font-medium text-text">{t("didoxDocument.ikpuTitle")}</p>
            <p className="mt-0.5 text-xs text-text-muted">{t("didoxDocument.ikpuHint")}</p>
          </div>
          <IkpuPicker companyId={companyId} taxId={taxId} value={ikpu} onChange={setIkpu} />
          {choice == null && (
            <p className="text-xs text-text-muted">{t("didoxDocument.ikpuRequired")}</p>
          )}
        </div>
      )}

      {blocking.length > 0 && (
        <Alert tone="warning" title={t("didoxDocument.blockedTitle")}>
          <ul className="space-y-1" data-testid="didox-doc-blockers">
            {blocking.map((code) => (
              <li key={code}>
                {/* `signer_identity_missing:31` carries the company it is about. */}
                {t(`didoxDocument.blockers.${code.split(":")[0]}`, {
                  defaultValue: code,
                })}
              </li>
            ))}
          </ul>
          {/* The signer is put on file by the Didox sign-in itself — the same
              signature over the ИНН — so this is one click here, not a trip to
              the company page and a second staff review. */}
          {isSeller && blocking.some((code) => code.startsWith("signer_identity_missing")) && (
            <div className="mt-2 space-y-1">
              <Button
                type="button"
                variant="secondary"
                disabled={session.minting}
                onClick={() =>
                  void session.open().then((opened) => {
                    if (opened) void prefill.refetch();
                  })
                }
                data-testid="didox-doc-sign-in"
              >
                {session.minting ? t("didox.connecting") : t("ikpu.session.open")}
              </Button>
              {session.error && (
                <p className="text-sm text-danger">{t(`didox.errors.${session.error}`)}</p>
              )}
            </div>
          )}
        </Alert>
      )}

      {isSeller && blocking.length === 0 && (
        <Button disabled={busy || !canCreate} onClick={() => void create()} data-testid="didox-doc-create">
          {busy ? t("didoxDocument.creating") : t("didoxDocument.create")}
        </Button>
      )}

      {error && (
        <p className="text-sm text-danger" data-testid="didox-doc-error">
          {t(`didoxDocument.errors.${error}`, { defaultValue: t("errors.generic") })}
        </p>
      )}
    </section>
  );
}
