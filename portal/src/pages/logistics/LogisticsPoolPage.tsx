import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { useActiveCompany } from "@/entities/company";
import { useLogisticsPool } from "@/entities/logistics-request";
import type { LogisticsPoolItem } from "@/entities/logistics-request";
import { LogisticsChat } from "@/features/logistics-chat";
import { logisticsRequestApi } from "@/entities/logistics-request";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatDate, formatQty } from "@/shared/lib";
import {
  Button,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  LoadingView,
  PageHeader,
  Tabs,
  TruckIcon,
} from "@/shared/ui";

/**
 * `/cabinet/requests` for a company whose confirmed role is logistics.
 *
 * A carrier files no polymer purchase requests, so «Заявки» was permanently
 * empty for it — this is what belongs in that slot: every open request a shipper
 * has broadcast, and the conversations this carrier has already started.
 *
 * The buyer's Заявки page is untouched; `RequestsRouteSwitch` picks between them.
 */
export function LogisticsPoolPage() {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const [tab, setTab] = useState<"all" | "mine">("all");
  const { activeCompany, isLoading } = useActiveCompany();
  const companyId = activeCompany?.id ?? null;
  const query = useLogisticsPool(companyId);

  // Deep-link target for the «новая заявка» notification, same trick as
  // `MarketRequestsPage`: open that card and scroll to it.
  const [searchParams] = useSearchParams();
  const deepLinked = searchParams.get("request");
  const [openId, setOpenId] = useState<number | null>(null);
  const scrolled = useRef(false);

  useEffect(() => {
    if (!deepLinked || scrolled.current || !query.data) return;
    const id = Number(deepLinked);
    if (!Number.isFinite(id)) return;
    scrolled.current = true;
    setOpenId(id);
    document
      .querySelector(`[data-request-id="${id}"]`)
      ?.scrollIntoView({ block: "center" });
  }, [deepLinked, query.data]);

  if (isLoading) return <LoadingView label={t("common.loading")} />;
  if (!activeCompany || companyId == null) {
    return (
      <ErrorView title={t("home.noActiveCompany")} message={t("home.noActiveCompanyBody")} />
    );
  }

  const items = query.data ?? [];
  const shown = tab === "mine" ? items.filter((i) => i.my_thread_id != null) : items;

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("logisticsRequest.poolTitle")}
        subtitle={t("logisticsRequest.poolSubtitle")}
      />

      {/* `min-w-0` is mandatory on a column holding Tabs — design-system rule. */}
      <div className="min-w-0">
        <Tabs
          items={[
            { id: "all", label: t("logisticsRequest.tabAll"), count: items.length },
            {
              id: "mine",
              label: t("logisticsRequest.tabMine"),
              count: items.filter((i) => i.my_thread_id != null).length,
            },
          ]}
          value={tab}
          onChange={(id) => setTab(id as "all" | "mine")}
          label={t("logisticsRequest.poolTitle")}
        />
      </div>

      {query.isLoading ? <LoadingView label={t("common.loading")} /> : null}

      {!query.isLoading && shown.length === 0 ? (
        <EmptyState
          icon={<TruckIcon size={24} />}
          title={t("logisticsRequest.poolEmptyTitle")}
          description={t(
            tab === "mine"
              ? "logisticsRequest.poolEmptyMineBody"
              : "logisticsRequest.poolEmptyBody",
          )}
        />
      ) : null}

      <ul className="space-y-2">
        {shown.map((item) => (
          <PoolCard
            key={item.id}
            item={item}
            companyId={companyId}
            lang={lang}
            open={openId === item.id}
            onToggle={() => setOpenId((c) => (c === item.id ? null : item.id))}
            onOpened={() => void query.refetch()}
          />
        ))}
      </ul>
    </div>
  );
}

interface PoolCardProps {
  item: LogisticsPoolItem;
  companyId: number;
  lang: string;
  open: boolean;
  onToggle: () => void;
  onOpened: () => void;
}

function PoolCard({ item, companyId, lang, open, onToggle, onOpened }: PoolCardProps) {
  const { t } = useTranslation();
  const [threadId, setThreadId] = useState<number | null>(item.my_thread_id);
  const [opening, setOpening] = useState(false);

  const endpoint = (country: string, city: string | null) =>
    [country === "other" ? null : countryName(country, lang), city]
      .filter(Boolean)
      .join(", ");

  async function reply(): Promise<void> {
    setOpening(true);
    try {
      // Idempotent server-side, so a second tap lands in the same room.
      const thread = await logisticsRequestApi.openThread(item.id, companyId);
      setThreadId(thread.id);
      onOpened();
      if (!open) onToggle();
    } finally {
      setOpening(false);
    }
  }

  return (
    <li data-request-id={item.id}>
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-text">{item.cargo_name}</p>
              <p className="mt-0.5 text-xs text-text-muted">
                {endpoint(item.from_country, item.from_city)} →{" "}
                {endpoint(item.to_country, item.to_city)}
                {" · "}
                {formatQty(item.volume, item.volume_unit, lang)}
              </p>
              <p className="mt-0.5 text-xs text-text-subtle">
                {item.buyer_name ?? "—"} · {formatDate(item.created_at, lang)}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="num text-xs text-text-muted">{item.number}</span>
              {threadId == null ? (
                <Button
                  size="sm"
                  loading={opening}
                  onClick={() => void reply()}
                  data-testid={`logistics-reply-${item.id}`}
                >
                  {t("logisticsRequest.reply")}
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onToggle}
                  data-testid={`logistics-open-${item.id}`}
                >
                  {t("logisticsRequest.openChat")}
                </Button>
              )}
            </div>
          </div>

          {item.special_requirements ? (
            <p className="text-xs leading-relaxed text-text-muted">
              {item.special_requirements}
            </p>
          ) : null}

          {open && threadId != null ? (
            <div className="border-t border-border pt-3">
              <LogisticsChat companyId={companyId} threadId={threadId} />
            </div>
          ) : null}
        </CardBody>
      </Card>
    </li>
  );
}
