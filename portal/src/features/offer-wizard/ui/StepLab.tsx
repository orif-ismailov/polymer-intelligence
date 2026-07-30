import { useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { LabOrderStatusBadge, useCreateLabOrder, useLabOrders } from "@/entities/lab";
import { MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from "@/shared/config";
import { formatBytes } from "@/shared/lib";
import {
  Alert,
  Badge,
  Button,
  CheckCircleIcon,
  CircleMinusIcon,
  CloseIcon,
  FileRow,
  FlaskIcon,
  ChoiceTile,
  InfoIcon,
  StepPanel,
  Textarea,
} from "@/shared/ui";

import { COUNTED_STEPS, PASSPORT_MIME, STEP_LAB } from "../model/constants";
import { useOfferDraft } from "../model/draftStore";
import { isLabValid } from "../model/validation";
import { StepNav } from "./StepNav";

interface StepLabProps {
  companyId: number;
  onNext: () => void;
  onBack: () => void;
}

/**
 * Sheet 5 — «Лабораторные данные».
 *
 * Two answers, both complete: attach the passport you have, or say you have
 * none and let us arrange the analysis. The order is raised immediately (it is a
 * request to us, not part of the listing) while the passport itself waits with
 * the rest of the draft — a file needs an offer id, and on a new offer there is
 * not one until the seller publishes.
 *
 * The badge the passport earns is NOT «Laboratory Verified»: that one is set
 * only when an analysis WE arranged finishes, and printing it over a
 * seller-uploaded PDF would sell our confirmation for free.
 */
export function StepLab({ companyId, onNext, onBack }: StepLabProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const draft = useOfferDraft((s) => s.draft);
  const setField = useOfferDraft((s) => s.setField);
  const offerId = useOfferDraft((s) => s.offerId);
  const passport = useOfferDraft((s) => s.labPassport);
  const setLabPassport = useOfferDraft((s) => s.setLabPassport);
  const serverFiles = useOfferDraft((s) => s.serverFiles);
  const removeServerFile = useOfferDraft((s) => s.removeServerFile);

  const orders = useLabOrders(offerId != null ? companyId : null);
  const createOrder = useCreateLabOrder(companyId);
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const serverPassport = serverFiles.find((f) => f.kind === "lab_passport") ?? null;
  const attached = passport !== null || serverPassport !== null;
  const myOrder =
    orders.data?.find((o) => o.offer_id === offerId && o.status !== "rejected") ?? null;
  const valid = isLabValid(draft, passport, serverPassport !== null);

  function choose(file: File | undefined): void {
    if (!file) return;
    if (file.type !== PASSPORT_MIME) {
      setError(t("lab.pdfOnly"));
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(t("offerWizard.documents.tooLarge", { mb: MAX_UPLOAD_MB }));
      return;
    }
    setError(null);
    setLabPassport(file);
    setField("hasPassport", true);
  }

  function handleNext(): void {
    setTouched(true);
    if (valid) onNext();
  }

  return (
    <StepPanel
      step={STEP_LAB}
      title={t("offerWizard.lab.title")}
      counter={t("offerWizard.stepOf", { current: STEP_LAB, total: COUNTED_STEPS })}
      data-testid="offer-wizard-step-5"
    >
      <p className="mb-3 flex items-center gap-1.5 text-sm font-medium text-text">
        {t("offerWizard.lab.heading")}
        <span className="text-text-subtle" title={t("offerWizard.lab.headingHint")}>
          <InfoIcon size={14} />
        </span>
      </p>

      <div className="grid grid-cols-2 gap-3">
        <ChoiceTile
          name="offer-passport"
          value="yes"
          checked={draft.hasPassport}
          onChange={() => setField("hasPassport", true)}
          icon={<CheckCircleIcon size={20} />}
          title={t("offerWizard.lab.hasPassport")}
          data-testid="offer-wizard-has-passport"
        />
        <ChoiceTile
          name="offer-passport"
          value="no"
          checked={!draft.hasPassport}
          onChange={() => {
            setField("hasPassport", false);
            setLabPassport(null);
          }}
          icon={<CircleMinusIcon size={20} />}
          title={t("offerWizard.lab.noPassport")}
          data-testid="offer-wizard-no-passport"
        />
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={PASSPORT_MIME}
        className="sr-only"
        onChange={(e) => {
          choose(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {draft.hasPassport ? (
        <div className="mt-4">
          <p className="mb-1.5 text-sm font-medium text-text">
            {t("offerWizard.lab.passportLabel")}
            <span className="ms-1 text-danger">*</span>
          </p>

          {attached ? (
            <div className="flex items-center gap-2">
              <FileRow
                className="min-w-0 flex-1"
                name={passport ? passport.file.name : (serverPassport?.file_name ?? "")}
                meta={passport ? `${formatBytes(passport.file.size)} · PDF` : "PDF"}
                icon={<FlaskIcon size={18} />}
                status={
                  <Badge tone="neutral" icon={<FlaskIcon />}>
                    {t("lab.badge.passport")}
                  </Badge>
                }
                actions={
                  <button
                    type="button"
                    aria-label={t("common.remove")}
                    onClick={() => {
                      if (passport) setLabPassport(null);
                      else if (serverPassport) removeServerFile(serverPassport.id);
                    }}
                    className="rounded-full p-1 text-text-subtle transition-colors hover:bg-danger hover:text-danger-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    <CloseIcon size={14} />
                  </button>
                }
              />
              <span className="shrink-0 text-brand" aria-hidden="true">
                <CheckCircleIcon size={18} />
              </span>
            </div>
          ) : (
            <Button variant="secondary" fullWidth onClick={() => inputRef.current?.click()}>
              {t("lab.upload")}
            </Button>
          )}

          {touched && !valid ? (
            <p role="alert" className="mt-1 text-xs text-danger">
              {t("offerWizard.lab.passportRequired")}
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <Alert tone="danger" className="mt-4">
          {error}
        </Alert>
      ) : null}

      {/* The offer to arrange it — the mockup's dark panel with the four bullets
          and the indigo CTA under them. */}
      <div className="mt-4 rounded-md border border-border bg-surface-inset px-4 py-3">
        <p className="flex items-start gap-2 text-xs leading-relaxed text-text-muted">
          <span className="mt-px shrink-0 text-info">
            <InfoIcon size={14} />
          </span>
          {t("offerWizard.lab.offerIntro")}
        </p>
        <p className="mt-3 text-sm font-medium text-text">{t("offerWizard.lab.offerWeWill")}</p>
        <ul className="mt-2 space-y-1.5">
          {(["accredited", "cost", "testing", "passport"] as const).map((point) => (
            <li key={point} className="flex items-start gap-2 text-xs text-text-muted">
              <span className="mt-0.5 shrink-0 text-brand">
                <CheckCircleIcon size={13} />
              </span>
              {t(`offerWizard.lab.points.${point}`)}
            </li>
          ))}
        </ul>

        {myOrder ? (
          <div className="mt-3 flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-2.5">
            <span className="min-w-0">
              <span className="num block text-sm font-medium text-text">{myOrder.number}</span>
              <span className="block text-xs text-text-muted">
                {myOrder.lab_partner_name ?? t("lab.partnerPending")}
              </span>
            </span>
            <LabOrderStatusBadge status={myOrder.status} />
          </div>
        ) : asking ? (
          <div className="mt-3 space-y-2">
            <Textarea
              rows={3}
              value={comment}
              placeholder={t("lab.orderCommentPlaceholder")}
              onChange={(e) => setComment(e.target.value)}
            />
            <Button
              fullWidth
              loading={createOrder.isPending}
              onClick={() =>
                createOrder.mutate(
                  { offer_id: offerId, comment: comment.trim() || null },
                  { onSuccess: () => setAsking(false) },
                )
              }
            >
              {t("lab.orderSubmit")}
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            fullWidth
            className="mt-3"
            onClick={() => setAsking(true)}
            data-testid="offer-wizard-lab-order"
          >
            <FlaskIcon size={16} />
            {t("offerWizard.lab.requestCta")}
          </Button>
        )}
      </div>

      <StepNav onNext={handleNext} onBack={onBack} />
    </StepPanel>
  );
}
