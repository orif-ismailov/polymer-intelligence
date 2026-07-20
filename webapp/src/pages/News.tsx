/**
 * Новости tab — classified market-news cards (Phase 7e) + the daily digest.
 *
 * Primary content is individual news article cards from /webapp/news/articles.
 * Phase 8a adds the top-nav scope tabs (All/Uzbekistan/Global/Producers), a search
 * box, a sort selector, and live facet filters (category/country/product) sourced from
 * /webapp/news/articles/filters. A compact "Сводка дня" banner links to the latest
 * published daily report (/news/:id). Cards open /news/article/:id.
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Newspaper, SlidersHorizontal } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import type {
  NewsArticleCard,
  NewsFilterOptions,
  NewsScope,
  NewsSort,
  NewsSummary,
} from "../types";

const IMPORTANCE_DOT: Record<string, string> = { high: "🔴", medium: "🟡", low: "⚪" };
const IMPACT_ARROW: Record<string, string> = { positive: "📈", negative: "📉", neutral: "➖" };

const SCOPES: NewsScope[] = ["all", "uzbekistan", "global", "producers"];
const SORTS: NewsSort[] = ["importance", "newest", "category", "products", "country", "company"];

export default function News() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [articles, setArticles] = useState<NewsArticleCard[]>([]);
  const [latestReport, setLatestReport] = useState<NewsSummary | null>(null);
  const [options, setOptions] = useState<NewsFilterOptions | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  // Filter state
  const [scope, setScope] = useState<NewsScope>("all");
  const [sort, setSort] = useState<NewsSort>("importance");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [country, setCountry] = useState<string | null>(null);
  const [product, setProduct] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(id);
  }, [search]);

  // The digest banner + filter facets load once.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([api.getNews(), api.getNewsFilters()]).then(([reports, opts]) => {
      if (cancelled) return;
      if (reports.status === "fulfilled" && reports.value.length > 0) {
        setLatestReport(reports.value[0] ?? null);
      }
      if (opts.status === "fulfilled") setOptions(opts.value);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Re-fetch the article list whenever a filter changes.
  useEffect(() => {
    let cancelled = false;
    setState("loading");
    api
      .getNewsArticles({
        scope,
        sort,
        q: debouncedSearch || undefined,
        category: category ?? undefined,
        country: country ?? undefined,
        product: product ?? undefined,
      })
      .then((rows) => {
        if (cancelled) return;
        setArticles(rows);
        setState("ok");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [scope, sort, debouncedSearch, category, country, product]);

  const hasActiveFilters = Boolean(category || country || product || debouncedSearch);
  const facetCount = useMemo(
    () => (options ? options.categories.length + options.countries.length + options.products.length : 0),
    [options],
  );

  function resetFilters() {
    setCategory(null);
    setCountry(null);
    setProduct(null);
    setSearch("");
    setDebouncedSearch("");
  }

  // A toggling facet chip: tapping the active value clears it.
  function facetChip(value: string, count: number, active: boolean, onToggle: () => void) {
    return (
      <button
        key={value}
        type="button"
        onClick={onToggle}
        style={{
          flex: "0 0 auto",
          padding: "5px 11px",
          borderRadius: "999px",
          fontSize: "12px",
          fontWeight: 600,
          cursor: "pointer",
          whiteSpace: "nowrap",
          border: active ? "1px solid var(--purple)" : "1px solid var(--border)",
          background: active ? "var(--purple)" : "var(--surface)",
          color: active ? "#fff" : "var(--text)",
        }}
      >
        {value}
        <span style={{ opacity: 0.6, marginInlineStart: "5px", fontWeight: 400 }}>{count}</span>
      </button>
    );
  }

  function facetRow(
    label: string,
    facets: { value: string; count: number }[],
    selected: string | null,
    setSelected: (v: string | null) => void,
  ) {
    if (facets.length === 0) return null;
    return (
      <div style={{ marginTop: "10px" }}>
        <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "6px" }}>{label}</div>
        <div style={{ display: "flex", gap: "6px", overflowX: "auto", paddingBottom: "2px" }}>
          {facets.map((f) =>
            facetChip(f.value, f.count, selected === f.value, () =>
              setSelected(selected === f.value ? null : f.value),
            ),
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 12px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("news.title")}
      </h1>

      {/* Search + sort + filter toggle */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "10px" }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("news.search")}
          aria-label={t("news.search")}
          style={{
            flex: 1,
            minWidth: 0,
            padding: "9px 12px",
            fontSize: "14px",
            borderRadius: "var(--r-md)",
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text)",
          }}
        />
        {facetCount > 0 && (
          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            aria-label={t("news.filters")}
            style={{
              flex: "0 0 auto",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "0 12px",
              borderRadius: "var(--r-md)",
              cursor: "pointer",
              border: showFilters || hasActiveFilters ? "1px solid var(--purple)" : "1px solid var(--border)",
              background: "var(--surface)",
              color: hasActiveFilters ? "var(--purple)" : "var(--text)",
              fontSize: "13px",
              fontWeight: 600,
            }}
          >
            <SlidersHorizontal size={15} />
          </button>
        )}
      </div>

      {/* Scope tabs (All / Uzbekistan / Global / Producers) */}
      <div style={{ display: "flex", gap: "6px", overflowX: "auto", marginBottom: "10px" }}>
        {SCOPES.map((s) => {
          const active = scope === s;
          return (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              style={{
                flex: "0 0 auto",
                padding: "7px 14px",
                borderRadius: "999px",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
                whiteSpace: "nowrap",
                border: active ? "1px solid var(--purple)" : "1px solid var(--border)",
                background: active ? "var(--purple)" : "var(--surface)",
                color: active ? "#fff" : "var(--text)",
              }}
            >
              {t(`news.scope.${s}`)}
            </button>
          );
        })}
      </div>

      {/* Sort + reset row */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
        <label style={{ fontSize: "12px", color: "var(--text-muted)" }} htmlFor="news-sort">
          {t("news.sort.label")}
        </label>
        <select
          id="news-sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as NewsSort)}
          style={{
            padding: "6px 8px",
            fontSize: "13px",
            borderRadius: "var(--r-sm)",
            border: "1px solid var(--border)",
            background: "var(--surface)",
            color: "var(--text)",
          }}
        >
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {t(`news.sort.${s}`)}
            </option>
          ))}
        </select>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={resetFilters}
            style={{
              marginInlineStart: "auto",
              padding: "6px 10px",
              fontSize: "12px",
              fontWeight: 600,
              borderRadius: "var(--r-sm)",
              border: "1px solid var(--border)",
              background: "var(--surface)",
              color: "var(--purple)",
              cursor: "pointer",
            }}
          >
            {t("news.reset")}
          </button>
        )}
      </div>

      {/* Collapsible facet filters */}
      {showFilters && options && (
        <div
          style={{
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            padding: "12px",
            marginBottom: "12px",
            background: "var(--surface)",
          }}
        >
          {facetRow(t("news.filterCategory"), options.categories, category, setCategory)}
          {facetRow(t("news.filterCountry"), options.countries, country, setCountry)}
          {facetRow(t("news.relatedProducts"), options.products, product, setProduct)}
        </div>
      )}

      {state === "error" && (
        <p style={{ color: "var(--danger)", fontSize: "14px" }}>{t("news.error")}</p>
      )}

      {/* Сводка дня — latest published daily report */}
      {latestReport && (
        <button
          type="button"
          onClick={() => navigate(`/news/${latestReport.id}`)}
          style={{
            display: "flex",
            width: "100%",
            textAlign: "start",
            alignItems: "center",
            gap: "12px",
            background: "var(--chip-neutral-bg)",
            border: "1px solid var(--purple)",
            borderRadius: "var(--r-md)",
            padding: "14px",
            marginBottom: "16px",
            cursor: "pointer",
            color: "var(--text)",
          }}
        >
          <FileText size={20} color="var(--purple)" style={{ flex: "0 0 auto" }} />
          <span>
            <span style={{ display: "block", fontSize: "15px", fontWeight: 600 }}>{t("news.digest")}</span>
            <span style={{ display: "block", fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
              {latestReport.title}
            </span>
          </span>
        </button>
      )}

      {state === "loading" && <p style={{ color: "var(--text-muted)", fontSize: "14px" }}>…</p>}

      {state === "ok" && articles.length === 0 && (
        <p style={{ color: "var(--text-muted)", fontSize: "14px", textAlign: "center", marginTop: "24px" }}>
          {hasActiveFilters ? t("news.noResults") : t("news.empty")}
        </p>
      )}

      {articles.map((a) => (
        <button
          key={a.id}
          type="button"
          onClick={() => navigate(`/news/article/${a.id}`)}
          style={{
            display: "block",
            width: "100%",
            textAlign: "start",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            boxShadow: "var(--shadow)",
            padding: "14px",
            marginBottom: "12px",
            cursor: "pointer",
            color: "var(--text)",
          }}
        >
          <span style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}>
            <span style={{ flex: "0 0 auto", fontSize: "14px", lineHeight: "20px" }}>
              {(a.importance && IMPORTANCE_DOT[a.importance]) || <Newspaper size={16} />}
              {a.market_impact ? IMPACT_ARROW[a.market_impact] : ""}
            </span>
            <span style={{ display: "block", fontSize: "15px", fontWeight: 600, lineHeight: 1.35 }}>
              {a.headline}
            </span>
          </span>

          {a.summary && (
            <span
              style={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                fontSize: "13px",
                color: "var(--text-muted)",
                marginTop: "6px",
                lineHeight: 1.45,
              }}
            >
              {a.summary}
            </span>
          )}

          <span
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "6px",
              alignItems: "center",
              marginTop: "10px",
              fontSize: "11px",
              color: "var(--text-muted)",
            }}
          >
            {a.source_name && <span>{a.source_name}</span>}
            {a.merged_count > 1 && (
              <span style={{ color: "var(--purple)", fontWeight: 600 }}>
                +{a.merged_count - 1} {t("news.sourcesLabel")}
              </span>
            )}
            {a.published_at && <span>· {a.published_at.slice(0, 10)}</span>}
            {a.related_products.slice(0, 3).map((p) => (
              <span
                key={p}
                style={{
                  padding: "1px 7px",
                  borderRadius: "999px",
                  background: "var(--chip-neutral-bg)",
                  color: "var(--purple)",
                  fontWeight: 600,
                }}
              >
                {p}
              </span>
            ))}
          </span>
        </button>
      ))}
    </div>
  );
}
