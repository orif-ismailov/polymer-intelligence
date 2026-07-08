/**
 * Новости tab — published daily market reports (IMG_0046 ④).
 *
 * Lists published reports from /webapp/news; tapping one opens the full report
 * (/news/:id). The branded report body is produced by the backend news engine.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Newspaper } from "lucide-react";

import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import type { NewsSummary } from "../types";

export default function News() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [items, setItems] = useState<NewsSummary[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    backButton.hide();
    mainButton.hide();
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getNews()
      .then((data) => {
        if (!cancelled) {
          setItems(data);
          setState("ok");
        }
      })
      .catch(() => {
        if (!cancelled) setState("error");
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
      {state === "ok" && items.length === 0 && (
        <p style={{ color: "var(--text-muted)", fontSize: "14px", textAlign: "center", marginTop: "24px" }}>
          {t("news.empty")}
        </p>
      )}

      {items.map((n) => (
        <button
          key={n.id}
          type="button"
          onClick={() => navigate(`/news/${n.id}`)}
          style={{
            display: "flex",
            width: "100%",
            textAlign: "start",
            alignItems: "center",
            gap: "12px",
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
          <span
            style={{
              flex: "0 0 auto",
              width: "40px",
              height: "40px",
              borderRadius: "var(--r-md)",
              background: "var(--chip-neutral-bg)",
              color: "var(--purple)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Newspaper size={20} />
          </span>
          <span>
            <span style={{ display: "block", fontSize: "15px", fontWeight: 600 }}>{n.title}</span>
            <span style={{ display: "block", fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
              {(n.published_at ?? n.period_start).slice(0, 10)}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}
