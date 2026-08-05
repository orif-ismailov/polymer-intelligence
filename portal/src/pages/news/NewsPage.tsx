import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useNewsArticles, type NewsArticle } from "@/entities/news";
import {
  Badge,
  Card,
  CardBody,
  EmptyState,
  ErrorView,
  PageHeader,
  Skeleton,
  NewspaperIcon,
} from "@/shared/ui";
import { formatDate, useTierBase } from "@/shared/lib";

function ArticleCard({ article, onOpen }: { article: NewsArticle; onOpen: () => void }) {
  const { t } = useTranslation();
  const isBreaking = article.importance === "high";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-lg"
    >
      <Card className="transition-colors hover:border-brand">
        <CardBody className="space-y-2">
          <div className="flex items-start justify-between gap-2">
            <span className="font-semibold text-text">{article.headline}</span>
            {isBreaking ? <Badge tone="danger">{t("news.breaking")}</Badge> : null}
          </div>
          {article.summary ? (
            <p className="line-clamp-2 text-sm text-text-muted">{article.summary}</p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-text-muted">
            {article.category ? <Badge tone="info">{article.category}</Badge> : null}
            {article.country ? <span>{article.country}</span> : null}
            {article.source_name ? <span>· {article.source_name}</span> : null}
            {article.published_at ? <span>· {formatDate(article.published_at)}</span> : null}
          </div>
        </CardBody>
      </Card>
    </button>
  );
}

export function NewsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const base = useTierBase();
  const newsQuery = useNewsArticles({ lang: i18n.language });

  return (
    <div className="space-y-5">
      <PageHeader title={t("news.title")} subtitle={t("news.subtitle")} />

      {newsQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : newsQuery.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void newsQuery.refetch()}
        />
      ) : newsQuery.data && newsQuery.data.length > 0 ? (
        <div className="space-y-3">
          {newsQuery.data.map((a) => (
            <ArticleCard key={a.id} article={a} onOpen={() => navigate(`${base}/news/${a.id}`)} />
          ))}
        </div>
      ) : (
        <EmptyState icon={<NewspaperIcon size={28} />} title={t("news.empty")} description={t("news.emptyBody")} />
      )}
    </div>
  );
}
