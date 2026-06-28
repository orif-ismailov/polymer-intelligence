/**
 * News detail (/news/:id) — full published report.
 *
 * Renders the backend-produced branded markdown body. We strip the lightweight
 * markdown emphasis markers (* _) and render as pre-wrapped text (emoji + bullets
 * preserved) — no markdown library, no HTML injection. BackButton → Новости.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import type { NewsItem } from "../types";

export default function NewsDetail() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<NewsItem | null>(null);
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
      .getNewsItem(Number(id))
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
  }, [id]);

  if (state !== "ok" || !item) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text-muted)", padding: "32px 16px", textAlign: "center" }}>
        {state === "error" ? t("news.error") : "…"}
      </div>
    );
  }

  const body = item.content_md.replace(/[*_]/g, "");

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "16px" }}>
      <h1 style={{ margin: "0 0 12px", fontSize: "20px", fontWeight: 700 }}>{item.title}</h1>
      <div
        style={{
          whiteSpace: "pre-wrap",
          fontSize: "14px",
          lineHeight: 1.6,
          color: "var(--text)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-md)",
          padding: "16px",
        }}
      >
        {body}
      </div>
    </div>
  );
}
