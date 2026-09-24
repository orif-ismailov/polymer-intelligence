import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import {
  TechOfferStatusBadge,
  useTechFeed,
  type TechFeedItem,
} from "@/entities/tech-request";
import { useOwnTechnologist } from "@/entities/technologist";
import { formatDate } from "@/shared/lib";
import {
  Alert,
  Badge,
  EmptyState,
  LinkButton,
  LoadingView,
  PageHeader,
  Tabs,
} from "@/shared/ui";

/**
 * `/cabinet/expert/requests` — every open «нужен технолог», for a listed expert.
 *
 * The factory is not named here: the job is public, who is asking is not, until
 * the two are talking. «Приглашения» narrows to the requests a factory pointed
 * at this expert from the catalog.
 */
export function ExpertRequestsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const invited = params.get("tab") === "invited";
  const own = useOwnTechnologist();
  const listed = own.data?.is_listed ?? false;
  const feed = useTechFeed(invited, listed);

  return (
    <div className="pb-10">
      <PageHeader title={t("expert.requests.title")} subtitle={t("expert.requests.subtitle")} />

      {own.data && !listed ? (
        <div className="mt-5">
          <Alert tone="info" title={t("expert.requests.notListed")}>
            <LinkButton to="/cabinet/expert" variant="outline" className="mt-3">
              {t("expert.requests.toProfile")}
            </LinkButton>
          </Alert>
        </div>
      ) : (
        <>
          <Tabs
            className="mt-4"
            label={t("expert.requests.title")}
            value={invited ? "invited" : "all"}
            onChange={(id) => setParams(id === "invited" ? { tab: "invited" } : {})}
            items={[
              { id: "all", label: t("expert.requests.all") },
              { id: "invited", label: t("expert.requests.invited") },
            ]}
          />
          {feed.isLoading || own.isLoading ? (
            <LoadingView label={t("common.loading")} />
          ) : feed.data && feed.data.length > 0 ? (
            <ul className="mt-4 grid gap-4 lg:grid-cols-2">
              {feed.data.map((item) => (
                <li key={item.id} className="min-w-0">
                  <FeedCard item={item} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              className="mt-4"
              title={t(invited ? "expert.requests.emptyInvited" : "expert.requests.empty")}
            />
          )}
        </>
      )}
    </div>
  );
}

function FeedCard({ item }: { item: TechFeedItem }) {
  const { t } = useTranslation();
  const place = [item.city, item.country].filter(Boolean).join(", ");
  return (
    <Link
      to={`/cabinet/expert/requests/${item.id}`}
      className="flex h-full flex-col gap-3 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-brand-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      data-testid="tech-feed-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="num text-xs text-text-subtle">{item.number}</p>
          <h3 className="mt-0.5 text-sm font-semibold text-text">
            {t(`technologists.need.${item.need_type}`)} · {item.product}
          </h3>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
          {item.invited ? <Badge tone="gold">{t("expert.requests.invitedBadge")}</Badge> : null}
          {item.urgency === "urgent" ? <Badge tone="danger">{t("technologists.urgency.urgent")}</Badge> : null}
          {item.my_offer ? <TechOfferStatusBadge status={item.my_offer.status} /> : null}
        </div>
      </div>
      <p className="line-clamp-2 text-sm text-text-muted">{item.problem}</p>
      <div className="flex flex-wrap gap-1.5">
        <Badge tone="brand">{t(`technologists.process.${item.process}`)}</Badge>
        {item.current_material ? <Badge>{item.current_material}</Badge> : null}
        {item.capacity ? (
          <Badge>
            {Number(item.capacity)} {t(`technologists.capacityUnit.${item.capacity_unit ?? "kg_h"}`)}
          </Badge>
        ) : null}
        <Badge>{t(`technologists.format.${item.work_format}`)}</Badge>
      </div>
      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3 text-xs text-text-muted">
        <span className="truncate">{item.company?.name ?? t("expert.requests.anonymousFactory")} · {place}</span>
        <span className="num shrink-0">{formatDate(item.created_at)}</span>
      </div>
    </Link>
  );
}
