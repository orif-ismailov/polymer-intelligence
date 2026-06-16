/**
 * Polymer Intelligence — Telegram Web App router shell.
 *
 * Honors Telegram theme CSS variables (var(--tg-theme-*)) per 03-UI-SPEC.md.
 * NO hardcoded dark colors — the Telegram client injects its own theme vars.
 * Sole exception: #ef4444 (destructive, per UI-SPEC §Color).
 *
 * Routes use React.lazy + Suspense for route-level code-splitting
 * (REQ-nfr-performance: ≤300 KB gzip bundle).
 */

import { lazy, Suspense, CSSProperties } from "react";
import { Routes, Route } from "react-router-dom";

// ── Shared style tokens (canonical source — reused by page components) ─────────

export const styles = {
  app: {
    minHeight: "100vh",
    backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
    color: "var(--tg-theme-text-color, #f8fafc)",
    fontFamily: "system-ui, sans-serif",
  } as CSSProperties,
  header: {
    padding: "16px",
    borderBottom: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
    backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
  } as CSSProperties,
  headerTitle: {
    margin: 0,
    fontSize: "18px",
    fontWeight: 600,
    color: "var(--tg-theme-text-color, #f8fafc)",
  } as CSSProperties,
  headerSubtitle: {
    margin: "4px 0 0",
    fontSize: "13px",
    color: "var(--tg-theme-hint-color, #94a3b8)",
  } as CSSProperties,
  main: {
    padding: "16px",
  } as CSSProperties,
  card: {
    borderRadius: "12px",
    padding: "16px",
    backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
    marginBottom: "12px",
  } as CSSProperties,
  cardTitle: {
    margin: "0 0 8px",
    fontSize: "15px",
    fontWeight: 600,
    color: "var(--tg-theme-text-color, #f8fafc)",
  } as CSSProperties,
  cardText: {
    margin: 0,
    fontSize: "13px",
    color: "var(--tg-theme-hint-color, #94a3b8)",
  } as CSSProperties,
  accentButton: {
    display: "block",
    width: "100%",
    minHeight: "44px",
    padding: "12px 20px",
    borderRadius: "8px",
    backgroundColor: "var(--tg-theme-button-color, #10b981)",
    color: "var(--tg-theme-button-text-color, #ffffff)",
    border: "none",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    boxSizing: "border-box" as const,
  } as CSSProperties,
} as const;

// ── Lazy-loaded routes (code-split by route) ───────────────────────────────────

const Home = lazy(() => import("./pages/Home"));
const Step1 = lazy(() => import("./pages/wizard/Step1"));
const Step2 = lazy(() => import("./pages/wizard/Step2"));
const Step3 = lazy(() => import("./pages/wizard/Step3"));
const Confirm = lazy(() => import("./pages/wizard/Confirm"));

// 03-05 screens — registered routes with placeholder components
const MyRequests = lazy(() => import("./pages/MyRequests"));
const RequestDetailPage = lazy(() => import("./pages/RequestDetail"));
const Notifications = lazy(() => import("./pages/Notifications"));
const SettingsPage = lazy(() => import("./pages/Settings"));

// ── Loading fallback ───────────────────────────────────────────────────────────

function PageLoader() {
  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: "32px",
          height: "32px",
          borderRadius: "50%",
          border: "3px solid var(--tg-theme-secondary-bg-color, #334155)",
          borderTopColor: "var(--tg-theme-button-color, #10b981)",
          animation: "spin 0.8s linear infinite",
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── App route table ────────────────────────────────────────────────────────────

export default function App() {
  return (
    <div style={styles.app}>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/request/step/1" element={<Step1 />} />
          <Route path="/request/step/2" element={<Step2 />} />
          <Route path="/request/step/3" element={<Step3 />} />
          <Route path="/request/confirm" element={<Confirm />} />
          <Route path="/requests" element={<MyRequests />} />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Suspense>
    </div>
  );
}
