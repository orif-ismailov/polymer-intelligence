import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useOpenRfqs } from "@/entities/deal";
import type { MarketRequest } from "@/entities/deal";
import { RfqResponseForm } from "@/features/rfq-response";
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
            <Badge tone="info">{t(`rfq.status.${request.my_response_status ?? "submitted"}`)}</Badge>
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

export function MarketRequestsPage() {
  const { t } = useTranslation();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const query = useOpenRfqs(companyId);
  // Set by the "new RFQ for you" bell (notificationLink → ?rfq=<id>).
  const [searchParams] = useSearchParams();
  const highlightedId = Number(searchParams.get("rfq")) || null;

  if (!activeCompany) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")}>
        <LinkButton to="/cabinet/companies/new/1">{t("companies.create")}</LinkButton>
      </ErrorView>
    );
  }

  const items = query.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader title={t("rfq.marketTitle")} subtitle={t("rfq.marketSubtitle")} />

      {query.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-56 w-full" />
        </div>
      ) : query.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void query.refetch()}
        />
      ) : items.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {items.map((request) => (
            <RequestCard
              key={request.id}
              request={request}
              companyId={activeCompany.id}
              onResponded={() => void query.refetch()}
              highlighted={request.id === highlightedId}
            />
          ))}
        </div>
      ) : (
        <EmptyState icon={<ClipboardListIcon size={28} />} title={t("rfq.marketEmpty")} description={t("rfq.marketEmptyBody")} />
      )}
    </div>
  );
}
