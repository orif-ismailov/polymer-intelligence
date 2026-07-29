import { useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { LabOrderStatusBadge, useCreateLabOrder, useLabOrders } from "@/entities/lab";
import { offerApi, type CompanyOffer } from "@/entities/offer";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  FileRow,
  FlaskIcon,
  Spinner,
  Textarea,
} from "@/shared/ui";

/** Server-side rule (`lab_service.RESULT_MIME`) — mirrored so the UI can say so
 *  before the round trip. A photo of a passport is not a passport. */
const ACCEPT = "application/pdf";

interface LabPassportBlockProps {
  companyId: number;
  /** Null while the offer is being created: files need an offer id to hang off. */
  offer: CompanyOffer | null;
  onUploaded: (offer: CompanyOffer) => void;
}

/**
 * The laboratory block of the offer form: upload a passport, or ask us to
 * arrange the analysis.
 *
 * Both routes end in the same badge on the market card, but they are not the
 * same claim — an order we ran also earns "Laboratory Verified", which is why
 * the copy next to the button says we will call to agree the laboratory, the
 * price and how to hand the sample over. Nothing here happens instantly.
 *
 * On a NEW offer the block is inert with an explanation: a file needs an offer
 * to attach to, and an analysis needs something to be about.
 */
export function LabPassportBlock({ companyId, offer, onUploaded }: LabPassportBlockProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [asking, setAsking] = useState(false);

  const orders = useLabOrders(offer ? companyId : null);
  const createOrder = useCreateLabOrder(companyId);

  const passport = offer?.files.find((f) => f.kind === "lab_passport") ?? null;
  const myOrder =
    orders.data?.find((o) => o.offer_id === offer?.id && o.status !== "rejected") ?? null;

  async function handleFile(file: File): Promise<void> {
    setError(null);
    if (file.type !== ACCEPT) {
      setError(t("lab.pdfOnly"));
      return;
    }
    if (!offer) return;
    setBusy(true);
    try {
      const updated = await offerApi.uploadFile(companyId, offer.id, file, "lab_passport");
      onUploaded(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleRemove(): Promise<void> {
    if (!offer || !passport) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await offerApi.deleteFile(companyId, offer.id, passport.id);
      onUploaded(updated);
    } catch (err) {
      // The one refusal worth spelling out: a result WE produced is evidence,
      // and the seller cannot take it down.
      setError(
        err instanceof Error && err.message.includes("lab_result_locked")
          ? t("lab.resultLocked")
          : t("errors.generic"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FlaskIcon />
          {t("lab.blockTitle")}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="text-sm text-text-muted">{t("lab.blockHint")}</p>

        {offer == null ? (
          <Alert tone="info">{t("lab.saveFirst")}</Alert>
        ) : passport ? (
          <FileRow
            name={passport.file_name}
            icon={<FlaskIcon size={18} />}
            status={
              offer.lab_verified ? (
                <Badge variant="lab-verified">{t("lab.badge.verified")}</Badge>
              ) : (
                <Badge tone="neutral" icon={<FlaskIcon />}>
                  {t("lab.badge.passport")}
                </Badge>
              )
            }
            actions={
              <Button variant="ghost" size="sm" onClick={handleRemove} disabled={busy}>
                {t("common.delete")}
              </Button>
            }
          />
        ) : (
          <div className="space-y-3">
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFile(file);
              }}
            />
            <div className="flex flex-wrap gap-3">
              <Button
                variant="secondary"
                onClick={() => inputRef.current?.click()}
                disabled={busy}
              >
                {busy ? <Spinner /> : null}
                {t("lab.upload")}
              </Button>
              {myOrder ? null : (
                <Button variant="ghost" onClick={() => setAsking((v) => !v)}>
                  {t("lab.orderCta")}
                </Button>
              )}
            </div>

            {asking && !myOrder ? (
              <div className="space-y-3 rounded-lg border border-border bg-surface-inset p-3">
                <p className="text-sm text-text-muted">{t("lab.orderCopy")}</p>
                <Textarea
                  rows={3}
                  value={comment}
                  placeholder={t("lab.orderCommentPlaceholder")}
                  onChange={(e) => setComment(e.target.value)}
                />
                <Button
                  loading={createOrder.isPending}
                  onClick={() =>
                    createOrder.mutate(
                      { offer_id: offer.id, comment: comment.trim() || null },
                      { onSuccess: () => setAsking(false) },
                    )
                  }
                >
                  {t("lab.orderSubmit")}
                </Button>
              </div>
            ) : null}
          </div>
        )}

        {myOrder ? (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border p-3">
            <span className="min-w-0">
              <span className="block text-sm font-medium text-text">{myOrder.number}</span>
              <span className="block text-xs text-text-muted">
                {myOrder.lab_partner_name ?? t("lab.partnerPending")}
              </span>
            </span>
            <LabOrderStatusBadge status={myOrder.status} />
          </div>
        ) : null}

        {error ? <Alert tone="danger">{error}</Alert> : null}
      </CardBody>
    </Card>
  );
}
