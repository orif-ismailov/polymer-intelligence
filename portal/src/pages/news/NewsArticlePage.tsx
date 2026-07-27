import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { useNewsArticle } from "@/entities/news";
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  LinkButton,
  LoadingView,
} from "@/shared/ui";
import { formatDate } from "@/shared/lib";

export function NewsArticlePage() {
  const { t, i18n } = useTranslation();
  const { signalId: idParam } = useParams<{ signalId: string }>();
  const signalId = idParam ? Number(idParam) : null;
  const articleQuery = useNewsArticle(signalId, i18n.language);

  if (articleQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (articleQuery.isError || !articleQuery.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger">{t("news.notFound")}</Alert>
        <LinkButton to="/news" variant="secondary">
          {t("news.back")}
        </LinkButton>
      </div>
    );
  }

  const a = articleQuery.data;
  const isBreaking = a.importance === "high";

  return (
    <article className="space-y-6">
      <LinkButton to="/news" variant="ghost" className="text-sm">
        ← {t("news.back")}
      </LinkButton>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          {isBreaking ? <Badge tone="danger">{t("news.breaking")}</Badge> : null}
          {a.category ? <Badge tone="info">{a.category}</Badge> : null}
          {a.country ? <Badge tone="neutral">{a.country}</Badge> : null}
        </div>
        <h1 className="text-2xl font-semibold text-text">{a.headline}</h1>
        <div className="text-sm text-text-muted">
          {a.source_name ? <span>{a.source_name}</span> : null}
          {a.published_at ? <span> · {formatDate(a.published_at)}</span> : null}
        </div>
      </header>

      {a.summary ? <p className="text-text">{a.summary}</p> : null}

      {a.analysis ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("news.analysis")}</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="whitespace-pre-line text-sm text-text-muted">{a.analysis}</p>
          </CardBody>
        </Card>
      ) : null}

      {a.recommendation ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("news.recommendation")}</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="whitespace-pre-line text-sm text-text-muted">{a.recommendation}</p>
          </CardBody>
        </Card>
      ) : null}

      {a.body ? (
        <p className="whitespace-pre-line text-sm text-text-muted">{a.body}</p>
      ) : null}

      {a.source_url ? (
        <a
          href={a.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-sm text-brand hover:underline"
        >
          {t("news.readSource")}
        </a>
      ) : null}
    </article>
  );
}
