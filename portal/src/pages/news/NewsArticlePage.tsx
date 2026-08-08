import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { normalizeMarketImpact, useNewsArticle, type NewsSourceRef } from "@/entities/news";
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  LinkButton,
  LoadingView,
  PageHeader,
} from "@/shared/ui";
import { formatDate } from "@/shared/lib";

const IMPORTANCE_TONE = { high: "danger", medium: "warning", low: "neutral" } as const;
const IMPACT_TONE = { positive: "success", negative: "danger", neutral: "neutral" } as const;

/** One labelled chip row — related products, countries, mentioned companies. */
function Chips({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h2 className="text-xs font-medium text-text-muted">{label}</h2>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {items.map((it) => (
          <li
            key={it}
            className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand"
          >
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * `/news/:signalId` — one classified article.
 *
 * There is one URL for this page. It used to resolve through `useTierBase()` so
 * that a cabinet visitor stayed inside `/cabinet`, but the cabinet twin is gone:
 * news is public, and a signed-in reader browses the same address as a crawler.
 */
export function NewsArticlePage() {
  const { t, i18n } = useTranslation();
  const { signalId: idParam } = useParams<{ signalId: string }>();
  const signalId = idParam ? Number(idParam) : null;
  const articleQuery = useNewsArticle(signalId, i18n.language);

  if (articleQuery.isLoading) return <LoadingView label={t("common.loading")} />;
  if (articleQuery.isError || !articleQuery.data) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-6 lg:px-6 lg:py-10">
        <Alert tone="danger">{t("news.notFound")}</Alert>
        <LinkButton to="/news" variant="secondary">
          {t("news.back")}
        </LinkButton>
      </div>
    );
  }

  const a = articleQuery.data;
  const importanceTone = IMPORTANCE_TONE[a.importance as keyof typeof IMPORTANCE_TONE];
  const impact = normalizeMarketImpact(a.market_impact);

  return (
    <article className="mx-auto max-w-3xl space-y-6 px-4 py-6 lg:px-6 lg:py-10">
      <PageHeader
        backTo="/news"
        backLabel={t("news.back")}
        title={a.headline}
        badge={
          <>
            {importanceTone ? (
              <Badge tone={importanceTone}>{t(`news.importance.${a.importance}`)}</Badge>
            ) : null}
            {impact && impact !== "neutral" ? (
              <Badge tone={IMPACT_TONE[impact]}>{t(`news.impact.${impact}`)}</Badge>
            ) : null}
            {a.category ? (
              <Badge tone="info">{t(`news.category.${a.category}`, a.category)}</Badge>
            ) : null}
            {a.country ? <Badge tone="neutral">{a.country}</Badge> : null}
          </>
        }
        subtitle={
          <>
            {a.source_name ? <span>{a.source_name}</span> : null}
            {a.published_at ? <span className="num"> · {formatDate(a.published_at)}</span> : null}
          </>
        }
      />

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

      {a.body ? <p className="whitespace-pre-line text-sm text-text-muted">{a.body}</p> : null}

      <Chips label={t("news.relatedProducts")} items={a.related_products} />
      <Chips label={t("news.countries")} items={a.countries} />
      <Chips label={t("news.companies")} items={a.companies} />

      {/*
        Cross-source merge (Phase 7f): when several outlets ran the same story
        they collapse into one card, and this is the only place that says so.
        The first entry is the representative one — the headline, summary and
        `source_url` above are ITS — so it is the one marked as the original.
      */}
      {a.sources.length > 1 ? (
        <div>
          <h2 className="text-xs font-medium text-text-muted">{t("news.sourcesLabel")}</h2>
          <ul className="mt-2 space-y-1">
            {a.sources.map((s: NewsSourceRef, i) => (
              <li key={s.id} className="text-sm text-text">
                {s.name || "—"}
                {s.published_at ? (
                  <span className="num text-text-muted"> · {formatDate(s.published_at)}</span>
                ) : null}
                {i === 0 ? (
                  <span className="text-text-muted"> — {t("news.original")}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
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
