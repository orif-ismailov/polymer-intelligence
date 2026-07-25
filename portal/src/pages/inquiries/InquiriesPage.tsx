import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import {
  useIncomingInquiries,
  useSentInquiries,
  type Inquiry,
} from "@/entities/inquiry";
import { Badge, Card, CardBody, EmptyState, ErrorView, LinkButton, Skeleton } from "@/shared/ui";
import { cn } from "@/shared/lib";

const STATUS_TONE = { pending: "warning", approved: "success", rejected: "danger" } as const;

type Tab = "sent" | "incoming";

function InquiryRow({ inquiry, onOpen }: { inquiry: Inquiry; onOpen: () => void }) {
  const { t } = useTranslation();
  const product = inquiry.offer.grade_text ?? inquiry.offer.product_text ?? `#${inquiry.offer_id}`;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-lg"
    >
      <Card className="transition-colors hover:border-accent">
        <CardBody className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium text-text">{product}</div>
            <div className="truncate text-sm text-text-muted">
              {inquiry.message ?? "—"}
            </div>
          </div>
          <Badge tone={STATUS_TONE[inquiry.status]}>{t(`inquiryStatus.${inquiry.status}`)}</Badge>
        </CardBody>
      </Card>
    </button>
  );
}

export function InquiriesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeCompany } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const [tab, setTab] = useState<Tab>("sent");

  const sent = useSentInquiries(companyId);
  const incoming = useIncomingInquiries(companyId);
  const active = tab === "sent" ? sent : incoming;

  if (!activeCompany) {
    return (
      <EmptyState
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t("inquiries.title")}</h1>
        <p className="mt-1 text-sm text-text-muted">{t("inquiries.subtitle")}</p>
      </div>

      <div className="flex gap-2 border-b border-border">
        {(["sent", "incoming"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === key
                ? "border-accent text-text"
                : "border-transparent text-text-muted hover:text-text",
            )}
          >
            {t(`inquiries.tab.${key}`)}
          </button>
        ))}
      </div>

      {active.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : active.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void active.refetch()}
        />
      ) : active.data && active.data.length > 0 ? (
        <div className="space-y-3">
          {active.data.map((inq) => (
            <InquiryRow
              key={inq.id}
              inquiry={inq}
              onOpen={() => navigate(`/inquiries/${inq.id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title={t(`inquiries.empty.${tab}`)}
          description={t("inquiries.emptyBody")}
          action={
            tab === "sent" ? (
              <LinkButton to="/market">{t("nav.market")}</LinkButton>
            ) : undefined
          }
        />
      )}
    </div>
  );
}
