/**
 * News article detail (/news/article/:id) — the "read more" for a classified card.
 *
 * Shows the headline, importance/impact markers, AI summary, the original article
 * body (plain text, no HTML injection), related products + companies chips, and a
 * link to the original source. BackButton → Новости.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import type { NewsArticleDetail } from "../types";

const IMPORTANCE_DOT: Record<string, string> = { high: "🔴", medium: "🟡", low: "⚪" };
const IMPACT_ARROW: Record<string, string> = { positive: "📈", negative: "📉", neutral: "➖" };

function Chips({ label, items, accent }: { label: string; items: string[]; accent: string }) {
  if (items.length === 0) return null;
  return (
    <div style={{ marginTop: "12px" }}>
      <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>{label}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
        {items.map((it) => (
          <span
            key={it}
            style={{
              padding: "3px 10px",
              borderRadius: "999px",
              background: "var(--chip-neutral-bg)",
              color: accent,
              fontSize: "12px",
              fontWeight: 600,
            }}
          >
            {it}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function NewsArticle() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<NewsArticleDetail | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/news"));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setState("loading");
    api
      .getNewsArticle(Number(id), i18n.language)
      .then((n) => {
        if (!cancelled) {
          setItem(n);
          setState("ok");
        }
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id, i18n.language]);

  if (state !== "ok" || !item) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text-muted)", padding: "32px 16px", textAlign: "center" }}>
        {state === "error" ? t("news.error") : "…"}
      </div>
    );
  }

  const marker =
    (item.importance ? IMPORTANCE_DOT[item.importance] ?? "" : "") +
    (item.market_impact ? IMPACT_ARROW[item.market_impact] ?? "" : "");

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "6px" }}>
        {marker} {item.source_name}
        {item.published_at ? ` · ${item.published_at.slice(0, 10)}` : ""}
      </div>

      <h1 dir="auto" style={{ margin: "0 0 12px", fontSize: "20px", fontWeight: 700, lineHeight: 1.3 }}>
        {item.headline}
      </h1>

      {item.summary && (
        <div
          dir="auto"
          style={{
            whiteSpace: "pre-wrap",
            fontSize: "14px",
            lineHeight: 1.6,
            background: "var(--surface)",
            border: "1px solid var(--purple)",
            borderRadius: "var(--r-md)",
            padding: "14px",
          }}
        >
          🤖 {item.summary}
        </div>
      )}

      {item.analysis && (
        <div style={{ marginTop: "12px" }}>
          <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--purple)", marginBottom: "4px" }}>
            {t("news.analysis")}
          </div>
          <div
            dir="auto"
            style={{
              whiteSpace: "pre-wrap",
              fontSize: "14px",
              lineHeight: 1.6,
              color: "var(--text)",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-md)",
              padding: "14px",
            }}
          >
            {item.analysis}
          </div>
        </div>
      )}

      {item.recommendation && (
        <div
          dir="auto"
          style={{
            display: "flex",
            gap: "8px",
            fontSize: "14px",
            fontWeight: 600,
            lineHeight: 1.5,
            color: "var(--text)",
            background: "var(--chip-neutral-bg)",
            border: "1px solid var(--purple)",
            borderRadius: "var(--r-md)",
            padding: "14px",
            marginTop: "12px",
          }}
        >
          <span style={{ flex: "0 0 auto" }}>💡</span>
          <span>
            <span style={{ display: "block", fontSize: "11px", fontWeight: 700, color: "var(--purple)", marginBottom: "2px" }}>
              {t("news.recommendation")}
            </span>
            {item.recommendation}
          </span>
        </div>
      )}

      {item.body && (
        <div
          dir="auto"
          style={{
            whiteSpace: "pre-wrap",
            fontSize: "14px",
            lineHeight: 1.6,
            color: "var(--text)",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            padding: "14px",
            marginTop: "12px",
          }}
        >
          {item.body}
        </div>
      )}

      <Chips label={t("news.relatedProducts")} items={item.related_products} accent="var(--purple)" />
      <Chips label={t("news.countries")} items={item.countries} accent="var(--text)" />
      <Chips label={t("news.companies")} items={item.companies} accent="var(--text)" />

      {item.sources.length > 1 && (
        <div style={{ marginTop: "12px" }}>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
            {t("news.sourcesLabel")}
          </div>
          {item.sources.map((s, i) => (
            <div key={s.id} style={{ fontSize: "13px", color: "var(--text)", marginBottom: "3px" }}>
              • {s.name || "—"}
              {s.published_at ? ` · ${s.published_at.slice(0, 10)}` : ""}
              {i === 0 && (
                <span style={{ color: "var(--text-muted)" }}> — {t("news.original")}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {item.source_url && (
        <a
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            marginTop: "16px",
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--purple)",
            textDecoration: "none",
          }}
        >
          <ExternalLink size={16} /> {t("news.readSource")}
        </a>
      )}
    </div>
  );
}
