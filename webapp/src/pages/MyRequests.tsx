/**
 * C-06 — My Requests screen ("Мои заявки").
 *
 * Displays the authenticated client's requests ordered by created_at DESC.
 * Features: 3-card loading skeleton, EmptyState for zero requests,
 * ErrorBanner on load failure, pull-to-refresh (haptic), visibility-change
 * refetch when the Web App is foregrounded (UI-SPEC §"Мои заявки").
 *
 * BackButton → Home (/).
 */

import { useEffect, useState, useCallback, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { styles } from "../App";
import { api } from "../api/client";
import { backButton, mainButton, impactLight } from "../telegram";
import RequestCard from "../components/RequestCard";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import type { RequestOut } from "../types";

// ── Loading skeleton (3 placeholder cards with pulsing animation) ─────────────

const SKELETON_STYLE: CSSProperties = {
  height: "72px",
  borderRadius: "12px",
  backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
  marginBottom: "12px",
  animation: "pulse 1.4s ease-in-out infinite",
};

function Skeleton() {
  return (
    <>
      <style>
        {`@keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }`}
      </style>
      <div style={SKELETON_STYLE} />
      <div style={SKELETON_STYLE} />
      <div style={SKELETON_STYLE} />
    </>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function MyRequests() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [requests, setRequests] = useState<RequestOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRequests = useCallback(async (withHaptic = false) => {
    setError(null);
    if (withHaptic) {
      impactLight();
    }
    try {
      const data = await api.getRequests();
      // Sort defensively by created_at DESC (API already returns newest-first,
      // but sort defensively per plan — UI-SPEC §"Мои заявки")
      const sorted = [...data].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      setRequests(sorted);
    } catch {
      setError(t("error.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Initial fetch
  useEffect(() => {
    void fetchRequests(false);
  }, [fetchRequests]);

  // Re-fetch when the Web App is foregrounded (UI-SPEC §"Мои заявки")
  useEffect(() => {
    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        setLoading(true);
        void fetchRequests(false);
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [fetchRequests]);

  // Telegram BackButton → Home
  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/"));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  // Pull-to-refresh: trigger on touch pull gesture using touchstart/touchend delta
  useEffect(() => {
    let startY = 0;
    function onTouchStart(e: TouchEvent) {
      startY = e.touches[0]?.clientY ?? 0;
    }
    function onTouchEnd(e: TouchEvent) {
      const endY = e.changedTouches[0]?.clientY ?? 0;
      const delta = endY - startY;
      // Only trigger if at top of page and pulled down ≥60px
      if (delta > 60 && window.scrollY === 0) {
        setLoading(true);
        void fetchRequests(true); // withHaptic=true for pull-to-refresh
      }
    }
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [fetchRequests]);

  function handleCardClick(id: number) {
    navigate(`/requests/${id}`);
  }

  return (
    <div style={{ ...styles.app, padding: "16px" }}>
      {/* Screen header */}
      <div style={styles.header as CSSProperties}>
        <h1 style={styles.headerTitle}>{t("myRequests.title")}</h1>
      </div>

      <div style={{ padding: "16px" }}>
        {/* Error banner */}
        {error && <ErrorBanner message={error} />}

        {/* Loading skeleton */}
        {loading && <Skeleton />}

        {/* Request list */}
        {!loading && !error && requests.length > 0 && (
          <div>
            {requests.map((req) => (
              <RequestCard key={req.id} request={req} onClick={handleCardClick} />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && requests.length === 0 && (
          <EmptyState
            heading={t("myRequests.empty.heading")}
            body={t("myRequests.empty.body")}
            cta={t("myRequests.empty.cta")}
            onCta={() => navigate("/")}
          />
        )}
      </div>
    </div>
  );
}
