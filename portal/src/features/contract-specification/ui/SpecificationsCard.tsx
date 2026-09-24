import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import {
  contractApi,
  contractKeys,
  useSpecifications,
} from "@/entities/contract";
import type { Specification } from "@/entities/contract";
import { DIDOX_STATUS, didoxApi } from "@/entities/edi";
import { useDidoxSession } from "@/features/didox-session";
import { useDidoxSign } from "@/features/didox-sign";
import { detailCode } from "@/shared/api";
import { formatDate, formatMoney } from "@/shared/lib";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
} from "@/shared/ui";

import { SpecificationForm } from "./SpecificationForm";

interface SpecificationsCardProps {
  contractId: number;
  companyId: number;
  taxId: string;
  /** The company can use Didox — without it nothing here can be sent or signed. */
  ready: boolean;
}

const TONE: Record<
  Specification["status"],
  "neutral" | "warning" | "success" | "danger"
> = {
  draft: "neutral",
  pending_signatures: "warning",
  active: "success",
  declined: "danger",
  cancelled: "neutral",
};

/**
 * «Спецификации» — the shipments of a signed framework contract.
 *
 * Either party draws one up; the SELLER sends it to Didox (a «Произвольный
 * документ» carrying our PDF) and signs it in the same click, the buyer signs
 * the incoming one. Once both have signed it is active and can be invoiced.
 */
export function SpecificationsCard({
  contractId,
  companyId,
  taxId,
  ready,
}: SpecificationsCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useSpecifications(contractId);
  const session = useDidoxSession(companyId, taxId);
  const didoxSign = useDidoxSign(companyId, taxId);
  const [formOpen, setFormOpen] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const data = query.data;
  if (!data || (!data.can_create && data.items.length === 0)) return null;

  async function refresh(): Promise<void> {
    await queryClient.invalidateQueries({
      queryKey: contractKeys.specifications(contractId),
    });
    await queryClient.invalidateQueries({ queryKey: ["didox", "factures"] });
  }

  async function openPdf(spec: Specification): Promise<void> {
    window.open(
      await contractApi.specificationUrl(contractId, spec.id),
      "_blank",
      "noopener",
    );
  }

  /** The seller: create at Didox, then sign — one click, like the договор. */
  async function sendAndSign(spec: Specification): Promise<void> {
    setBusyId(spec.id);
    setError(null);
    try {
      const created = await session.withSession(() =>
        didoxApi.createSpecificationDocument(companyId, spec.id),
      );
      await didoxSign.sign(created.id);
    } catch (err) {
      setError(detailCode(err) ?? "failed");
    } finally {
      setBusyId(null);
      await refresh();
    }
  }

  async function sign(spec: Specification): Promise<void> {
    if (spec.didox_document_id == null) return;
    setBusyId(spec.id);
    try {
      await didoxSign.sign(spec.didox_document_id);
    } finally {
      setBusyId(null);
      await refresh();
    }
  }

  async function cancel(spec: Specification): Promise<void> {
    setBusyId(spec.id);
    try {
      await contractApi.cancelSpecification(contractId, spec.id);
    } finally {
      setBusyId(null);
      await refresh();
    }
  }

  return (
    <Card data-testid="specifications">
      <CardHeader>
        <CardTitle>{t("specification.title")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        {data.items.length === 0 ? (
          <p className="text-sm text-text-muted">{t("specification.none")}</p>
        ) : (
          <ul
            className="divide-y divide-border text-sm"
            data-testid="specification-list"
          >
            {data.items.map((spec) => {
              const ours = spec.didox_status === DIDOX_STATUS.draft;
              const theirsToSign =
                spec.didox_status === DIDOX_STATUS.awaitingUs;
              const busy = busyId === spec.id || didoxSign.signing;
              return (
                <li
                  key={spec.id}
                  className="space-y-2 py-3"
                  data-testid="specification-row"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium text-text">
                      {t("specification.name", { n: spec.number })}
                      <span className="ms-2 text-text-muted">
                        {formatDate(spec.spec_date)}
                      </span>
                    </p>
                    <Badge tone={TONE[spec.status]}>
                      {t(`specification.status.${spec.status}`)}
                    </Badge>
                  </div>
                  <p className="text-text-muted">
                    {spec.lines.map((l) => l.product).join(", ")} ·{" "}
                    <span className="num">
                      {formatMoney(spec.amount_with_vat, "UZS")}
                    </span>
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {spec.document_available ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => void openPdf(spec)}
                      >
                        {t("specification.openPdf")}
                      </Button>
                    ) : null}
                    {ready && data.is_seller && spec.status === "draft" ? (
                      <Button
                        size="sm"
                        disabled={busy}
                        onClick={() => void sendAndSign(spec)}
                        data-testid="specification-send"
                      >
                        {busy ? t("didox.signing") : t("didox.signAndSend")}
                      </Button>
                    ) : null}
                    {ready &&
                    spec.status === "pending_signatures" &&
                    (ours || theirsToSign) ? (
                      <Button
                        size="sm"
                        disabled={busy}
                        onClick={() => void sign(spec)}
                        data-testid="specification-sign"
                      >
                        {busy ? t("didox.signing") : t("didox.signAndSend")}
                      </Button>
                    ) : null}
                    {spec.status === "draft" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void cancel(spec)}
                      >
                        {t("contracts.actions.cancel")}
                      </Button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {didoxSign.error ? (
          <p className="text-sm text-danger">
            {t(`didox.signErrors.${didoxSign.error}`, {
              message: didoxSign.errorMessage ?? "",
            })}
          </p>
        ) : null}
        {error ? (
          <p className="text-sm text-danger" data-testid="specification-error">
            {t(`didoxDocument.errors.${error}`, {
              defaultValue: t("errors.generic"),
            })}
          </p>
        ) : null}

        {data.can_create && !formOpen ? (
          <Button
            variant="secondary"
            onClick={() => setFormOpen(true)}
            data-testid="specification-new"
          >
            {t("specification.new")}
          </Button>
        ) : null}
        {formOpen ? (
          <SpecificationForm
            contractId={contractId}
            onCancel={() => setFormOpen(false)}
            onCreated={() => {
              setFormOpen(false);
              void refresh();
            }}
          />
        ) : null}
      </CardBody>
    </Card>
  );
}
