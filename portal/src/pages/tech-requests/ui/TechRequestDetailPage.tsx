import { useMemo, useState } from "react";

import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import {
  ContactsCard,
  TECH_CHAT_POLL_MS,
  TechOfferStatusBadge,
  TechRequestFacts,
  TechRequestStatusBadge,
  techThreadChatApi,
  useCancelTechRequest,
  useCompanyTechOffers,
  useCompanyTechRequest,
  useCompleteTechRequest,
  useDecideTechOffer,
  useOpenCompanyThread,
  useTechReview,
  type CompanyOffer,
} from "@/entities/tech-request";
import { TechnologistSummary } from "@/entities/technologist";
import { ThreadChat } from "@/features/thread-chat";
import { formatMoney } from "@/shared/lib";
import {
  Alert,
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  Dialog,
  EmptyState,
  ErrorView,
  FormField,
  LoadingView,
  PageHeader,
  StarIcon,
  Textarea,
  ToggleChips,
} from "@/shared/ui";

/**
 * `/cabinet/tech-requests/:requestId` — the factory's side of one request.
 *
 * Offers arrive here; each has its own conversation (one thread per expert —
 * no expert reads a competitor's terms). Accepting one declines the rest and
 * reveals both sides' contacts; the work itself happens off-platform, and
 * «Работа выполнена» closes the request with the review that feeds the
 * expert's rating.
 */
export function TechRequestDetailPage() {
  const { t } = useTranslation();
  const { requestId } = useParams();
  const id = requestId && /^\d+$/.test(requestId) ? Number(requestId) : null;
  const { activeCompanyId } = useActiveCompany();
  const request = useCompanyTechRequest(activeCompanyId, id);
  const offers = useCompanyTechOffers(activeCompanyId, id);
  const cancel = useCancelTechRequest(activeCompanyId, id);
  const decide = useDecideTechOffer(activeCompanyId, id);
  const openThread = useOpenCompanyThread(activeCompanyId, id);
  const review = useTechReview(activeCompanyId, id, request.data?.status === "completed");
  const [chatWith, setChatWith] = useState<{ threadId: number; name: string } | null>(null);
  const [confirm, setConfirm] = useState<null | { kind: "accept" | "decline"; offer: CompanyOffer } | { kind: "cancel" }>(null);
  const [completeOpen, setCompleteOpen] = useState(false);
  const chatApi = useMemo(() => techThreadChatApi(activeCompanyId), [activeCompanyId]);

  if (request.isLoading) return <LoadingView label={t("common.loading")} />;
  if (!request.data) return <ErrorView title={t("techRequest.notFound")} />;
  const r = request.data;
  const accepted = offers.data?.find((o) => o.status === "accepted") ?? null;

  function openChat(offer: CompanyOffer): void {
    const name = offer.technologist.full_name ?? t("technologists.untitled");
    if (offer.thread_id) {
      setChatWith({ threadId: offer.thread_id, name });
      return;
    }
    openThread.mutate(offer.profile_id, {
      onSuccess: (thread) => setChatWith({ threadId: thread.id, name }),
    });
  }

  return (
    <div className="pb-10">
      <PageHeader
        backTo="/cabinet/tech-requests"
        backLabel={t("techRequest.listTitle")}
        title={`${t(`technologists.need.${r.need_type}`)} · ${r.product}`}
        badge={<TechRequestStatusBadge status={r.status} />}
        subtitle={r.number}
        actions={
          <div className="flex flex-wrap gap-2">
            {r.status === "assigned" ? (
              <Button onClick={() => setCompleteOpen(true)} data-testid="tech-complete">
                {t("techRequest.complete")}
              </Button>
            ) : null}
            {r.status === "open" || r.status === "assigned" ? (
              <Button variant="ghost" onClick={() => setConfirm({ kind: "cancel" })}>
                {t("techRequest.cancel")}
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="min-w-0 space-y-6">
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-text">
                {t("techRequest.offers")} <span className="num text-text-muted">{offers.data?.length ?? 0}</span>
              </h2>
              {r.status === "open" ? (
                <Link to="/technologists" className="text-sm text-brand hover:underline">
                  {t("techRequest.inviteMore")}
                </Link>
              ) : null}
            </div>
            {offers.isLoading ? (
              <LoadingView label={t("common.loading")} />
            ) : offers.data && offers.data.length > 0 ? (
              offers.data.map((offer) => (
                <OfferCard
                  key={offer.id}
                  offer={offer}
                  requestOpen={r.status === "open"}
                  onChat={() => openChat(offer)}
                  onAccept={() => setConfirm({ kind: "accept", offer })}
                  onDecline={() => setConfirm({ kind: "decline", offer })}
                />
              ))
            ) : (
              <EmptyState title={t("techRequest.noOffers")} description={t("techRequest.noOffersBody")} />
            )}
          </section>

          {chatWith ? (
            <Card>
              <CardBody className="space-y-3">
                <h2 className="text-sm font-semibold text-text">
                  {t("techRequest.chatWith", { name: chatWith.name })}
                </h2>
                <ThreadChat
                  companyId={activeCompanyId ?? 0}
                  threadId={chatWith.threadId}
                  api={chatApi}
                  pollMs={TECH_CHAT_POLL_MS}
                />
              </CardBody>
            </Card>
          ) : null}
        </div>

        <aside className="space-y-4">
          {accepted?.contacts ? (
            <ContactsCard contacts={accepted.contacts} title={t("techRequest.expertContacts")} />
          ) : null}
          {review.data ? (
            <Card>
              <CardBody className="space-y-2">
                <h2 className="text-sm font-semibold text-text">{t("techRequest.yourReview")}</h2>
                <p className="inline-flex items-center gap-1 text-sm text-text">
                  <StarIcon size={14} className="text-gold" />
                  <span className="num font-semibold">{review.data.rating}</span>/5
                </p>
                {review.data.text ? <p className="text-sm text-text-muted">{review.data.text}</p> : null}
              </CardBody>
            </Card>
          ) : null}
          <Card>
            <CardBody>
              <TechRequestFacts request={r} />
            </CardBody>
          </Card>
        </aside>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm?.kind === "accept"
            ? t("techRequest.acceptConfirm")
            : confirm?.kind === "decline"
              ? t("techRequest.declineConfirm")
              : t("techRequest.cancelConfirm")
        }
        description={confirm?.kind === "accept" ? t("techRequest.acceptHint") : undefined}
        confirmLabel={
          confirm?.kind === "accept"
            ? t("techRequest.accept")
            : confirm?.kind === "decline"
              ? t("techRequest.decline")
              : t("techRequest.cancel")
        }
        cancelLabel={t("common.cancel")}
        danger={confirm?.kind !== "accept"}
        loading={decide.isPending || cancel.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (!confirm) return;
          if (confirm.kind === "cancel") {
            cancel.mutate(undefined, { onSettled: () => setConfirm(null) });
          } else {
            decide.mutate(
              { offerId: confirm.offer.id, accept: confirm.kind === "accept" },
              { onSettled: () => setConfirm(null) },
            );
          }
        }}
      />

      <CompleteDialog
        open={completeOpen}
        companyId={activeCompanyId}
        requestId={r.id}
        onClose={() => setCompleteOpen(false)}
      />
    </div>
  );
}

function OfferCard({
  offer,
  requestOpen,
  onChat,
  onAccept,
  onDecline,
}: {
  offer: CompanyOffer;
  requestOpen: boolean;
  onChat: () => void;
  onAccept: () => void;
  onDecline: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Card data-testid="tech-offer-card">
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <Link to={`/technologists/${offer.technologist.id}`} className="min-w-0 flex-1 hover:opacity-90">
            <TechnologistSummary card={offer.technologist} />
          </Link>
          <TechOfferStatusBadge status={offer.status} />
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span className="num font-semibold text-text">{formatMoney(offer.price, offer.currency)}</span>
          <span className="text-text-muted">{t("techOffer.daysValue", { count: offer.duration_days })}</span>
          <span className="text-text-muted">{t(`technologists.format.${offer.work_format}`)}</span>
        </div>
        <p className="whitespace-pre-line text-sm text-text-muted">{offer.scope}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onChat}>
            {t("techRequest.write")}
          </Button>
          {requestOpen && offer.status === "submitted" ? (
            <>
              <Button size="sm" onClick={onAccept} data-testid="tech-accept">
                {t("techRequest.accept")}
              </Button>
              <Button variant="ghost" size="sm" onClick={onDecline}>
                {t("techRequest.decline")}
              </Button>
            </>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

function CompleteDialog({
  open,
  companyId,
  requestId,
  onClose,
}: {
  open: boolean;
  companyId: number | null;
  requestId: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const complete = useCompleteTechRequest(companyId, requestId);
  const [rating, setRating] = useState<string[]>(["5"]);
  const [text, setText] = useState("");

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("techRequest.completeTitle")}
      description={t("techRequest.completeHint")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            loading={complete.isPending}
            disabled={rating.length === 0}
            onClick={() =>
              complete.mutate(
                { rating: Number(rating[0]), text: text.trim() || null },
                { onSuccess: onClose },
              )
            }
            data-testid="tech-complete-confirm"
          >
            {t("techRequest.complete")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <FormField label={t("techRequest.rating")} required>
          {() => (
            <ToggleChips
              label={t("techRequest.rating")}
              single
              options={["1", "2", "3", "4", "5"]}
              value={rating}
              onChange={setRating}
              renderLabel={(o) => `${o} ★`}
            />
          )}
        </FormField>
        <FormField label={t("techRequest.reviewText")}>
          {({ id }) => <Textarea id={id} rows={3} value={text} onChange={(e) => setText(e.target.value)} />}
        </FormField>
        {complete.isError ? <Alert tone="danger" title={t("errors.generic")} /> : null}
      </div>
    </Dialog>
  );
}

