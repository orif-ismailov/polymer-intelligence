import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import {
  ContactsCard,
  TECH_CHAT_POLL_MS,
  TechOfferStatusBadge,
  TechRequestFacts,
  TechRequestStatusBadge,
  techThreadChatApi,
  useOpenExpertThread,
  useTechFeedItem,
  useTechOfferAction,
} from "@/entities/tech-request";
import { TechOfferForm } from "@/features/tech-offer";
import { ThreadChat } from "@/features/thread-chat";
import { formatMoney } from "@/shared/lib";
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  ErrorView,
  LoadingView,
  PageHeader,
  SpecItem,
  SpecList,
} from "@/shared/ui";

/** Built once: `ThreadChat` reads its api through a ref, but a stable object is cheaper still. */
const EXPERT_CHAT_API = techThreadChatApi(null);

/**
 * `/cabinet/expert/requests/:requestId` — one request, from the expert's side:
 * the brief, their offer, the conversation with the factory, and — once the
 * factory accepts — the factory's contacts.
 */
export function ExpertRequestPage() {
  const { t } = useTranslation();
  const { requestId } = useParams();
  const id = requestId && /^\d+$/.test(requestId) ? Number(requestId) : null;
  const query = useTechFeedItem(id);
  const openThread = useOpenExpertThread(id ?? 0);
  const offerAction = useTechOfferAction(id ?? 0);
  const [editing, setEditing] = useState(false);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);

  if (query.isLoading) return <LoadingView label={t("common.loading")} />;
  if (!query.data) return <ErrorView title={t("techRequest.notFound")} />;

  const item = query.data;
  const offer = item.my_offer;
  const activeOffer = offer && (offer.status === "submitted" || offer.status === "accepted") ? offer : null;
  const canOffer = item.status === "open" && !activeOffer;

  return (
    <div className="pb-10">
      <PageHeader
        backTo="/cabinet/expert/requests"
        backLabel={t("expert.requests.title")}
        title={`${t(`technologists.need.${item.need_type}`)} · ${item.product}`}
        badge={<TechRequestStatusBadge status={item.status} />}
        subtitle={`${item.number} · ${item.company?.name ?? t("expert.requests.anonymousFactory")}`}
      />

      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardBody>
              <TechRequestFacts request={item} />
            </CardBody>
          </Card>

          <Card>
            <CardBody className="space-y-3">
              <h2 className="text-sm font-semibold text-text">{t("techRequest.chat")}</h2>
              {item.my_thread_id ? (
                <ThreadChat
                  companyId={0}
                  threadId={item.my_thread_id}
                  api={EXPERT_CHAT_API}
                  pollMs={TECH_CHAT_POLL_MS}
                />
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-text-muted">{t("expert.request.askHint")}</p>
                  <Button
                    variant="outline"
                    loading={openThread.isPending}
                    onClick={() => openThread.mutate()}
                    data-testid="expert-ask"
                  >
                    {t("expert.request.ask")}
                  </Button>
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-4">
          {item.contacts ? (
            <ContactsCard contacts={item.contacts} title={t("expert.request.factoryContacts")} />
          ) : null}

          <Card>
            <CardBody className="space-y-4">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-text">{t("expert.request.myOffer")}</h2>
                {offer ? <TechOfferStatusBadge status={offer.status} /> : null}
              </div>

              {activeOffer && !editing ? (
                <>
                  <SpecList>
                    <SpecItem
                      label={t("techOffer.price")}
                      value={formatMoney(activeOffer.price, activeOffer.currency)}
                      numeric
                    />
                    <SpecItem label={t("techOffer.days")} value={activeOffer.duration_days} numeric />
                    <SpecItem
                      label={t("techRequest.form.workFormat")}
                      value={t(`technologists.format.${activeOffer.work_format}`)}
                    />
                  </SpecList>
                  <p className="whitespace-pre-line text-sm text-text-muted">{activeOffer.scope}</p>
                  {activeOffer.status === "submitted" && item.status === "open" ? (
                    <div className="flex gap-2">
                      <Button variant="outline" className="flex-1" onClick={() => setEditing(true)}>
                        {t("common.edit")}
                      </Button>
                      <Button variant="ghost" className="flex-1" onClick={() => setConfirmWithdraw(true)}>
                        {t("techOffer.withdraw")}
                      </Button>
                    </div>
                  ) : null}
                </>
              ) : canOffer || editing ? (
                <TechOfferForm
                  requestId={item.id}
                  existing={editing ? activeOffer : null}
                  defaultFormat={item.work_format}
                  onDone={() => setEditing(false)}
                />
              ) : (
                <p className="text-sm text-text-muted">
                  {t(item.status === "open" ? "expert.request.offerClosed" : "expert.request.requestClosed")}
                </p>
              )}
            </CardBody>
          </Card>
        </aside>
      </div>

      <ConfirmDialog
        open={confirmWithdraw}
        title={t("techOffer.withdrawConfirm")}
        confirmLabel={t("techOffer.withdraw")}
        cancelLabel={t("common.cancel")}
        onClose={() => setConfirmWithdraw(false)}
        loading={offerAction.isPending}
        danger
        onConfirm={() =>
          offerAction.mutate({ action: "withdraw" }, { onSettled: () => setConfirmWithdraw(false) })
        }
      />
    </div>
  );
}
