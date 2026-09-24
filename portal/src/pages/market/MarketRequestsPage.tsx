import { useEffect, useId, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import {
  TenderDeadlineBadge,
  TenderList,
  TenderRow,
  useMyRfqResponses,
  useOpenRfqs,
} from "@/entities/deal";
import type { MarketRequest, OpenRfqFilters } from "@/entities/deal";
import { MyQuoteRow, RfqResponseForm } from "@/features/rfq-response";
import {
  Button,
  Card,
  ChevronDownIcon,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  Tabs,
  type TabItem,
  ClipboardListIcon,
} from "@/shared/ui";
import { cn } from "@/shared/lib";

import { parseQuoteStatus } from "./quoteStatus";
import { OpenTenderFilters, QuoteStatusFilter } from "./TenderFilters";

/**
 * One open buyer tender a supplier company may quote against.
 *
 * The payload is anonymized server-side — trade terms only, no buyer contacts —
 * so there is nothing to hide here; the platform stays the intermediary until a
 * deal opens. «Ответить» unfolds the quote form under the row rather than on a
 * separate page, so the tender's terms stay in view while it is filled in.
 */
function OpenTenderRow({
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
  const responded = request.my_response_id != null;
  const [open, setOpen] = useState(Boolean(highlighted) && !responded);
  const rowRef = useRef<HTMLLIElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (highlighted) rowRef.current?.scrollIntoView({ block: "center" });
  }, [highlighted]);

  const docs = request.required_docs.map((code) => t(`rfq.docs.${code}`)).join(", ");

  return (
    <TenderRow
      request={request}
      rowRef={rowRef}
      highlighted={highlighted}
      statusLabel={t("rfq.columns.responseWindow")}
      status={<TenderDeadlineBadge request={request} />}
      detail={
        docs ? <p className="mt-1 text-sm text-text-muted">{t("rfq.needs", { docs })}</p> : null
      }
      action={
        responded ? (
          <LinkButton
            to={`/cabinet/market/requests?tab=mine&response=${request.my_response_id}`}
            variant="outline"
            size="sm"
            fullWidth
          >
            {t("rfq.viewMyQuote")}
          </LinkButton>
        ) : (
          <Button
            size="sm"
            variant={open ? "ghost" : "primary"}
            fullWidth
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? t("rfq.hideForm") : t("rfq.reply")}
            <ChevronDownIcon
              size={16}
              className={cn("transition-transform", open && "rotate-180")}
            />
          </Button>
        )
      }
      panelId={panelId}
      panel={
        open && !responded ? (
          <RfqResponseForm
            companyId={companyId}
            requestId={request.id}
            onSubmitted={() => {
              setOpen(false);
              onResponded();
            }}
            onCancel={() => setOpen(false)}
          />
        ) : null
      }
    />
  );
}

/** Placeholder rows shaped like the list, so the page does not jump on load. */
function TenderListSkeleton() {
  return (
    <Card className="divide-y divide-border p-0">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <Skeleton className="h-10 flex-1" />
          <Skeleton className="hidden h-6 w-24 md:block" />
          <Skeleton className="hidden h-6 w-32 md:block" />
          <Skeleton className="h-9 w-32" />
        </div>
      ))}
    </Card>
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

  // Filters live in the URL beside the tab, for the same reason: a filtered view
  // is something a supplier bookmarks («срочные по PP»).
  const productParam = Number(searchParams.get("product")) || null;
  const filters: OpenRfqFilters = {
    ...(productParam ? { productId: productParam } : {}),
    closingSoon: searchParams.get("closing") === "1",
    urgent: searchParams.get("urgent") === "1",
    unanswered: searchParams.get("unanswered") === "1",
  };
  const filtered = productParam != null || filters.closingSoon || filters.urgent || filters.unanswered;
  const quoteStatus = parseQuoteStatus(searchParams.get("status"));

  const openQuery = useOpenRfqs(companyId, filters);
  const mineQuery = useMyRfqResponses(companyId, quoteStatus ?? undefined);
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

  /** Writes one URL param (`null` drops it), leaving the tab and the rest alone. */
  function setParam(key: string, value: string | null): void {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value == null) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  const TOGGLE_PARAM = { closingSoon: "closing", urgent: "urgent", unanswered: "unanswered" } as const;

  function resetFilters(): void {
    setSearchParams(tab === "mine" ? { tab: "mine" } : {}, { replace: true });
  }

  function selectTab(next: string): void {
    // Drop the highlight params with the tab that owned them — a stale ?rfq=
    // would otherwise keep re-scrolling the other list on every switch.
    setSearchParams(next === "mine" ? { tab: "mine" } : {}, { replace: true });
  }

  return (
    <div className="space-y-5">
      <PageHeader title={t("rfq.marketTitle")} subtitle={t("rfq.marketSubtitle")} />

      <Tabs items={tabs} value={tab} onChange={selectTab} label={t("rfq.marketTitle")} />

      {tab === "open" ? (
        <OpenTenderFilters
          filters={filters}
          onProductChange={(id) => setParam("product", id != null ? String(id) : null)}
          onToggle={(key, on) => setParam(TOGGLE_PARAM[key], on ? "1" : null)}
          onReset={resetFilters}
        />
      ) : (
        <QuoteStatusFilter status={quoteStatus} onChange={(status) => setParam("status", status)} />
      )}

      {active.isLoading ? (
        <TenderListSkeleton />
      ) : active.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void active.refetch()}
        />
      ) : tab === "open" ? (
        openItems.length > 0 ? (
          <TenderList statusHeading={t("rfq.columns.responseWindow")}>
            {openItems.map((request) => (
              <OpenTenderRow
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
          </TenderList>
        ) : filtered ? (
          <EmptyState
            icon={<ClipboardListIcon size={28} />}
            title={t("rfq.filters.empty")}
            description={t("rfq.filters.emptyBody")}
            action={
              <Button variant="outline" size="sm" onClick={resetFilters}>
                {t("rfq.filters.reset")}
              </Button>
            }
          />
        ) : (
          <EmptyState icon={<ClipboardListIcon size={28} />} title={t("rfq.marketEmpty")} description={t("rfq.marketEmptyBody")} />
        )
      ) : myQuotes.length > 0 ? (
        <TenderList statusHeading={t("rfq.columns.yourQuote")}>
          {myQuotes.map((quote) => (
            <MyQuoteRow
              key={quote.id}
              quote={quote}
              companyId={activeCompany.id}
              highlighted={quote.id === highlightedQuoteId}
            />
          ))}
        </TenderList>
      ) : quoteStatus ? (
        <EmptyState
          icon={<ClipboardListIcon size={28} />}
          title={t("rfq.filters.mineEmpty")}
          description={t("rfq.filters.mineEmptyBody")}
          action={
            <Button variant="outline" size="sm" onClick={resetFilters}>
              {t("rfq.filters.reset")}
            </Button>
          }
        />
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
