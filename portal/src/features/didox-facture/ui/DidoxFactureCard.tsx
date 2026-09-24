import { useEffect, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { DIDOX_STATUS, didoxApi } from "@/entities/edi";
import type { DidoxContractLine, DidoxFactures } from "@/entities/edi";
import { useDidoxSession } from "@/features/didox-session";
import { useDidoxSign } from "@/features/didox-sign";
import { IkpuPicker, ikpuChoiceOf } from "@/features/ikpu-picker";
import type { IkpuValue } from "@/features/ikpu-picker";
import { detailCode, detailError } from "@/shared/api";
import { formatDate, formatMoney } from "@/shared/lib";
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  LinkButton,
  Select,
} from "@/shared/ui";

interface DidoxFactureCardProps {
  companyId: number;
  /** The acting company's ИНН — sessions and certificates are matched by it. */
  taxId: string;
  contractId: number;
  /**
   * The acting company can use Didox (account + signed offer). Until then the
   * card lists invoices but offers no action — the click would reach Didox only
   * to be refused after the key password.
   */
  ready: boolean;
}

/** A form line: numbers as typed, VAT as the Select holds it. */
interface DraftLine {
  name: string;
  count: string;
  price: string;
  vat: string;
}

const NO_VAT = "none";

/** `"10.000"` → `"10"`, `"1150.50"` → `"1150.5"` — the column's scale is not the user's. */
function trimDecimal(value: string | null): string {
  if (value == null) return "";
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

function draftFrom(data: DidoxFactures): DraftLine[] {
  return data.lines.map((line) => ({
    name: line.name,
    count: trimDecimal(line.count),
    price: trimDecimal(line.price),
    vat: line.vat_rate == null ? NO_VAT : String(line.vat_rate),
  }));
}

function isPositive(value: string): boolean {
  const n = Number(value.replace(",", "."));
  return Number.isFinite(n) && n > 0;
}

/**
 * «Счета-фактуры» — the ЭСФ (Didox 002) of a signed contract.
 *
 * The seller issues one per shipment: the form starts from what is left to
 * invoice, and one button creates the invoice at Didox and signs it — there is
 * no reason to create an ЭСФ and not sign it. The buyer sees each invoice and
 * signs the ones waiting on them.
 *
 * An ЭСФ is in soum. A contract priced in another currency starts with an empty
 * price and a hint, rather than «1150» that would invoice 1150 сум.
 */
export function DidoxFactureCard({
  companyId,
  taxId,
  contractId,
  ready,
}: DidoxFactureCardProps) {
  const { t } = useTranslation();
  const session = useDidoxSession(companyId, taxId);
  const didoxSign = useDidoxSign(companyId, taxId);
  const [formOpen, setFormOpen] = useState(false);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [ikpu, setIkpu] = useState<IkpuValue | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["didox", "factures", companyId, contractId],
    queryFn: () => didoxApi.factures(companyId, contractId),
  });
  const data = query.data;

  useEffect(() => {
    if (formOpen && data) setLines(draftFrom(data));
  }, [formOpen, data]);

  if (!data) return null;
  // Nothing to show a buyer before the first invoice exists.
  if (!data.is_seller && data.documents.length === 0) return null;

  const blocking = [
    ...data.blockers.filter((code) => code !== "not_seller"),
    ...(ready ? [] : ["didox_not_ready"]),
  ];
  const choice = ikpuChoiceOf(ikpu);
  const notInSoum =
    data.currency != null && data.currency.toUpperCase() !== "UZS";
  const linesValid =
    lines.length > 0 &&
    lines.every((l) => isPositive(l.count) && isPositive(l.price));
  const canIssue =
    data.is_seller &&
    blocking.length === 0 &&
    data.pending_document_id == null &&
    linesValid &&
    (!data.ikpu_choice || choice != null);

  async function signAndRefresh(documentId: number): Promise<void> {
    await didoxSign.sign(documentId);
    await query.refetch();
  }

  async function issue(): Promise<void> {
    setBusy(true);
    setError(null);
    const payload: DidoxContractLine[] = lines.map((l) => ({
      name: l.name,
      count: l.count.replace(",", "."),
      price: l.price.replace(",", "."),
      vat_rate: l.vat === NO_VAT ? null : Number(l.vat),
    }));
    let documentId: number;
    try {
      // A missing Didox session is minted with the key on the first 409.
      const created = await session.withSession(() =>
        didoxApi.createFacture(
          companyId,
          contractId,
          payload,
          data?.ikpu_choice ? choice : null,
        ),
      );
      documentId = created.id;
    } catch (err) {
      setError(detailCode(err) ?? detailError(err) ?? "failed");
      setBusy(false);
      await query.refetch();
      return;
    }
    try {
      setFormOpen(false);
      await signAndRefresh(documentId);
    } finally {
      setBusy(false);
    }
  }

  function setLine(index: number, patch: Partial<DraftLine>): void {
    setLines((current) =>
      current.map((l, i) => (i === index ? { ...l, ...patch } : l)),
    );
  }

  return (
    <Card data-testid="didox-factures">
      <CardHeader>
        <CardTitle>{t("facture.title")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {data.documents.length === 0 ? (
          <p className="text-sm text-text-muted">{t("facture.none")}</p>
        ) : (
          <ul
            className="divide-y divide-border text-sm"
            data-testid="facture-list"
          >
            {data.documents.map((doc) => {
              // Ours to sign: our own draft, or theirs awaiting us.
              const signable =
                ready &&
                ((doc.outgoing && doc.status === DIDOX_STATUS.draft) ||
                  (!doc.outgoing && doc.status === DIDOX_STATUS.awaitingUs));
              return (
                <li
                  key={doc.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-text">
                      {doc.number ?? `#${doc.id}`}
                      <span className="ms-2 text-text-muted">
                        {formatDate(doc.doc_date)}
                      </span>
                    </p>
                    <p className="text-text-muted">
                      {formatMoney(doc.total, "UZS")} ·{" "}
                      {t(`didox.documentStatus.${doc.status}`, {
                        defaultValue: String(doc.status),
                      })}
                    </p>
                  </div>
                  {signable ? (
                    <Button
                      size="sm"
                      disabled={didoxSign.signing}
                      onClick={() => void signAndRefresh(doc.id)}
                      data-testid="facture-sign"
                    >
                      {didoxSign.signing
                        ? t("didox.signing")
                        : t("didox.signAndSend")}
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}

        {didoxSign.error ? (
          <p className="text-sm text-danger" data-testid="facture-sign-error">
            {t(`didox.signErrors.${didoxSign.error}`, {
              message: didoxSign.errorMessage ?? "",
            })}
          </p>
        ) : null}

        {!ready ? (
          <div className="space-y-2">
            <p className="text-sm text-text-muted">
              {t("facture.didoxNotReady")}
            </p>
            <LinkButton to="/cabinet/didox" size="sm" variant="secondary">
              {t("didox.connect")}
            </LinkButton>
          </div>
        ) : null}

        {ready &&
        data.is_seller &&
        blocking.length > 0 &&
        !blocking.includes("not_active") ? (
          <Alert tone="warning" title={t("facture.blockedTitle")}>
            <ul className="space-y-1" data-testid="facture-blockers">
              {blocking.map((code) => (
                <li key={code}>
                  {t(`facture.blockers.${code.split(":")[0]}`, {
                    defaultValue: t(
                      `didoxDocument.blockers.${code.split(":")[0]}`,
                      {
                        defaultValue: code,
                      },
                    ),
                  })}
                </li>
              ))}
            </ul>
          </Alert>
        ) : null}

        {data.is_seller &&
        blocking.length === 0 &&
        data.pending_document_id != null ? (
          <p className="text-sm text-text-muted">{t("facture.pending")}</p>
        ) : null}

        {data.is_seller &&
        blocking.length === 0 &&
        data.pending_document_id == null &&
        !formOpen ? (
          <Button
            variant="secondary"
            onClick={() => setFormOpen(true)}
            data-testid="facture-new"
          >
            {t("facture.new")}
          </Button>
        ) : null}

        {formOpen ? (
          <div
            className="space-y-4 rounded-md border border-border p-4"
            data-testid="facture-form"
          >
            {notInSoum ? (
              <Alert tone="info">
                {t("facture.notInSoum", { currency: data.currency })}
              </Alert>
            ) : null}
            {lines.map((line, index) => (
              <div key={index} className="space-y-3">
                <p className="text-sm font-medium text-text">
                  {line.name}
                  {data.lines[index]?.unit ? (
                    <span className="ms-1 text-text-muted">
                      ({data.lines[index]?.unit})
                    </span>
                  ) : null}
                </p>
                <div className="grid gap-3 sm:grid-cols-3">
                  <FormField label={t("facture.count")} required>
                    {({ id }) => (
                      <Input
                        id={id}
                        inputMode="decimal"
                        value={line.count}
                        onChange={(e) =>
                          setLine(index, { count: e.target.value })
                        }
                        data-testid="facture-count"
                      />
                    )}
                  </FormField>
                  <FormField label={t("facture.price")} required>
                    {({ id }) => (
                      <Input
                        id={id}
                        inputMode="decimal"
                        value={line.price}
                        onChange={(e) =>
                          setLine(index, { price: e.target.value })
                        }
                        data-testid="facture-price"
                      />
                    )}
                  </FormField>
                  <FormField label={t("facture.vat")}>
                    {({ id }) => (
                      <Select
                        id={id}
                        value={line.vat}
                        onChange={(e) =>
                          setLine(index, { vat: e.target.value })
                        }
                        options={[
                          { value: "12", label: "12%" },
                          { value: "0", label: "0%" },
                          { value: NO_VAT, label: t("facture.noVat") },
                        ]}
                        data-testid="facture-vat"
                      />
                    )}
                  </FormField>
                </div>
              </div>
            ))}

            {data.ikpu_choice ? (
              <div className="space-y-2" data-testid="facture-ikpu">
                <p className="text-sm font-medium text-text">
                  {t("didoxDocument.ikpuTitle")}
                </p>
                <IkpuPicker
                  companyId={companyId}
                  taxId={taxId}
                  value={ikpu}
                  onChange={setIkpu}
                />
                {choice == null ? (
                  <p className="text-xs text-text-muted">
                    {t("didoxDocument.ikpuRequired")}
                  </p>
                ) : null}
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button
                disabled={busy || !canIssue}
                onClick={() => void issue()}
                data-testid="facture-issue"
              >
                {busy ? t("facture.issuing") : t("facture.issue")}
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => setFormOpen(false)}
              >
                {t("common.cancel")}
              </Button>
            </div>
          </div>
        ) : null}

        {error ? (
          <p className="text-sm text-danger" data-testid="facture-error">
            {t(`facture.errors.${error}`, {
              defaultValue: t(`didoxDocument.errors.${error}`, {
                defaultValue: t("errors.generic"),
              }),
            })}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
