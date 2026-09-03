import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { RfqResponseStatusBadge, useMyRfqResponses, useOpenRfqs } from "@/entities/deal";
import type { MarketRequest } from "@/entities/deal";
import { MyQuoteCard, RfqResponseForm } from "@/features/rfq-response";
import { formatDate } from "@/shared/lib";
import {
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  SpecItem,
  SpecList,
  Tabs,
  type TabItem,
  ClipboardListIcon,
} from "@/shared/ui";

/**
 * Open buyer RFQs a supplier company may quote against.
 *
 * The payload is anonymized server-side — trade terms only, no buyer contacts —
 * so there is nothing to hide here; the platform stays the intermediary until a
 * deal opens.
 */
function RequestCard({
  request,
  companyId,
  onResponded,
  highlighted,
}: {
  request: MarketRequest;
  companyId: number;
  onResponded: () => void;
  /** Arrived here from the "new RFQ for you" bell — open and scroll to it. */
  highlighted?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(Boolean(highlighted) && request.my_response_id == null);
  const cardRef = useRef<HTMLDivElement>(null);
  const responded = request.my_response_id != null;

  useEffect(() => {
    if (highlighted) cardRef.current?.scrollIntoView({ block: "center" });
  }, [highlighted]);

  return (
    // A wrapper div carries the ref: Card is a plain function component, and
    // making a shared primitive forwardRef for one scroll target is not worth it.
    <div ref={cardRef}>
    <Card className={highlighted ? "border-brand" : undefined}>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold text-text">{request.product ?? "—"}</p>
            {request.grade ? (
              <p className="truncate text-xs text-text-muted">{request.grade}</p>
            ) : null}
          </div>
          {responded ? (
            <RfqResponseStatusBadge status={request.my_response_status ?? "submitted"} />
          ) : null}
        </div>

        <SpecList>
          <SpecItem
            label={t("rfq.volume")}
            value={`${request.volume} ${request.volume_unit}`}
            numeric
          />
          <SpecItem label={t("rfq.incoterms")} value={request.incoterms} />
          <SpecItem
            label={t("rfq.destination")}
            value={[request.port_or_city, request.destination_country].filter(Boolean).join(", ")}
          />
          <SpecItem
            label={t("rfq.desiredDate")}
            value={request.desired_date ? formatDate(request.desired_date) : "—"}
            numeric
          />
        </SpecList>

        {request.required_docs.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-text-subtle">{t("rfq.requiredDocs")}:</span>
            {request.required_docs.map((code) => (
              <Badge key={code} tone="gold">
                {t(`rfq.docs.${code}`)}
              </Badge>
            ))}
          </div>
        ) : null}

        {open ? (
          <div className="border-t border-border pt-3">
            <RfqResponseForm
              companyId={companyId}
              requestId={request.id}
              onSubmitted={() => {
                setOpen(false);
                onResponded();
              }}
              onCancel={() => setOpen(false)}
            />
          </div>
        ) : (
          <div className="border-t border-border pt-3">
            <Button disabled={responded} onClick={() => setOpen(true)}>
              {responded ? t("rfq.alreadyResponded") : t("rfq.respond")}
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
    </div>
  );
}

type Tab = "open" | "mine";

/**
 * The supplier's two views of the same object: tenders they may still answer,
 * and the answers they have already given.
 *
 * The tab lives in the URL rather than in state — «Предложение не выбрано»
 * deep-links straight to `?tab=mine&response=<id>`, and that only works if the
 * page can be addressed in that condition.
 */
export function MarketRequestsPage() {
  const { t } = useTranslation();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "mine" ? "mine" : "open";

  const openQuery = useOpenRfqs(companyId);
  const mineQuery = useMyRfqResponses(companyId);
  const active = tab === "mine" ? mineQuery : openQuery;

  // Set by the bells: ?rfq=<request id> on the open tab, ?response=<quote id> on ours.
  const highlightedId = Number(searchParams.get("rfq")) || null;
  const highlightedQuoteId = Number(searchParams.get("response")) || null;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const openItems = openQuery.data?.items ?? [];
  const myQuotes = mineQuery.data?.items ?? [];
  const tabs: TabItem[] = (["open", "mine"] as const).map((key) => ({
    id: key,
    label: t(`rfq.tab.${key}`),
    testId: `rfq-tab-${key}`,
  }));

  function selectTab(next: string): void {
    // Drop the highlight params with the tab that owned them — a stale ?rfq=
    // would otherwise keep re-scrolling the other list on every switch.
    setSearchParams(next === "mine" ? { tab: "mine" } : {}, { replace: true });
  }

  return (
    <div className="space-y-5">
      <PageHeader title={t("rfq.marketTitle")} subtitle={t("rfq.marketSubtitle")} />

      <Tabs items={tabs} value={tab} onChange={selectTab} label={t("rfq.marketTitle")} />

      {active.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-56 w-full" />
        </div>
      ) : active.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void active.refetch()}
        />
      ) : tab === "open" ? (
        openItems.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {openItems.map((request) => (
              <RequestCard
                key={request.id}
                request={request}
                companyId={activeCompany.id}
                onResponded={() => {
                  void openQuery.refetch();
                  void mineQuery.refetch();
                }}
                highlighted={request.id === highlightedId}
              />
            ))}
          </div>
        ) : (
          <EmptyState icon={<ClipboardListIcon size={28} />} title={t("rfq.marketEmpty")} description={t("rfq.marketEmptyBody")} />
        )
      ) : myQuotes.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {myQuotes.map((quote) => (
            <MyQuoteCard
              key={quote.id}
              quote={quote}
              companyId={activeCompany.id}
              highlighted={quote.id === highlightedQuoteId}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ClipboardListIcon size={28} />}
          title={t("rfq.mine.empty")}
          description={t("rfq.mine.emptyBody")}
        />
      )}
    </div>
  );
}
