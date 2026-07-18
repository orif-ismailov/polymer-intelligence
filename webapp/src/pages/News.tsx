/**
 * Новости tab — classified market-news cards (Phase 7e) + the daily digest.
 *
 * Primary content is individual news article cards from /webapp/news/articles
 * (ranked importance→recency). A compact "Сводка дня" banner at the top links to
 * the latest published daily report (/news/:id). Cards open /news/article/:id.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Newspaper } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import type { NewsArticleCard, NewsSummary } from "../types";

const IMPORTANCE_DOT: Record<string, string> = { high: "🔴", medium: "🟡", low: "⚪" };
const IMPACT_ARROW: Record<string, string> = { positive: "📈", negative: "📉", neutral: "➖" };

export default function News() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [articles, setArticles] = useState<NewsArticleCard[]>([]);
  const [latestReport, setLatestReport] = useState<NewsSummary | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([api.getNewsArticles(), api.getNews()])
      .then(([arts, reports]) => {
        if (cancelled) return;
        if (arts.status === "fulfilled") setArticles(arts.value);
        if (reports.status === "fulfilled" && reports.value.length > 0) {
          setLatestReport(reports.value[0] ?? null);
        }
        // Error only when BOTH surfaces failed — otherwise show what we have.
        setState(arts.status === "rejected" && reports.status === "rejected" ? "error" : "ok");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div style={{ padding: "16px" }}>
      <h1 style={{ margin: "0 0 16px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
        {t("news.title")}
      </h1>

      {state === "loading" && <p style={{ color: "var(--text-muted)", fontSize: "14px" }}>…</p>}
      {state === "error" && <p style={{ color: "var(--danger)", fontSize: "14px" }}>{t("news.error")}</p>}

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

      {state === "ok" && articles.length === 0 && !latestReport && (
        <p style={{ color: "var(--text-muted)", fontSize: "14px", textAlign: "center", marginTop: "24px" }}>
          {t("news.empty")}
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
