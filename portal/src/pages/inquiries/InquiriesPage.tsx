import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import {
  useIncomingInquiries,
  useSentInquiries,
  type Inquiry,
} from "@/entities/inquiry";
import {
  Badge,
  Card,
  CardBody,
  ChevronRightIcon,
  EmptyState,
  ErrorView,
  LinkButton,
  PageHeader,
  Skeleton,
  Tabs,
  type TabItem,
  InboxIcon,
  RegistryIcon,
} from "@/shared/ui";

const STATUS_TONE = { pending: "warning", approved: "success", rejected: "danger" } as const;

type Tab = "sent" | "incoming";

function InquiryRow({ inquiry, onOpen }: { inquiry: Inquiry; onOpen: () => void }) {
  const { t } = useTranslation();
  const product = inquiry.offer.grade_text ?? inquiry.offer.product_text ?? `#${inquiry.offer_id}`;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-lg"
    >
      <Card className="transition-colors hover:border-brand-line">
        <CardBody className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium text-text">{product}</div>
            <div className="truncate text-sm text-text-muted">
              {inquiry.message ?? "—"}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <Badge tone={STATUS_TONE[inquiry.status]}>{t(`inquiryStatus.${inquiry.status}`)}</Badge>
            <span className="text-text-subtle">
              <ChevronRightIcon size={16} />
            </span>
          </div>
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
          icon={<RegistryIcon size={28} />}
        title={t("home.noActiveCompany")}
        description={t("home.noActiveCompanyBody")}
      />
    );
  }

  const inquiryTabs: TabItem[] = (["sent", "incoming"] as const).map((key) => ({
    id: key,
    label: t(`inquiries.tab.${key}`),
  }));

  return (
    <div className="space-y-5">
      <PageHeader title={t("inquiries.title")} subtitle={t("inquiries.subtitle")} />

      <Tabs items={inquiryTabs} value={tab} onChange={(id) => setTab(id as Tab)} label={t("inquiries.title")} />

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
              onOpen={() => navigate(`/cabinet/inquiries/${inq.id}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<InboxIcon size={28} />}
          title={t(`inquiries.empty.${tab}`)}
          description={t("inquiries.emptyBody")}
          action={
            tab === "sent" ? (
              <LinkButton to="/cabinet/market">{t("nav.market")}</LinkButton>
            ) : undefined
          }
        />
      )}
    </div>
  );
}
