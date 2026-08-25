import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { didoxApi } from "@/entities/edi";
import { ApiError } from "@/shared/api";
import { Alert, Button, LinkButton } from "@/shared/ui";

interface DidoxDocumentCardProps {
  companyId: number;
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
 */
export function DidoxDocumentCard({ companyId, contractId, onCreated }: DidoxDocumentCardProps) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const prefill = useQuery({
    queryKey: ["didox", "contract-prefill", companyId, contractId],
    queryFn: () => didoxApi.contractPrefill(companyId, contractId),
  });

  if (prefill.isLoading || !prefill.data) return null;
  const data = prefill.data;

  // Already at the operator: the signing controls take over from here.
  if (data.document_id != null) return null;

  const isSeller = companyId === data.seller_company_id;
  const blocking = data.blockers.filter((code) => code !== "not_seller");

  async function create(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await didoxApi.createContractDocument(companyId, contractId);
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
          {blocking.some((code) => code.startsWith("signer_identity_missing")) && (
            <LinkButton to={`/cabinet/companies/${companyId}`} variant="secondary" className="mt-2">
              {t("didoxDocument.confirmIdentity")}
            </LinkButton>
          )}
        </Alert>
      )}

      {isSeller && blocking.length === 0 && (
        <Button disabled={busy} onClick={() => void create()} data-testid="didox-doc-create">
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
