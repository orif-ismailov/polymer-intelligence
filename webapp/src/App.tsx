/**
 * PetroAI — Telegram Web App router shell.
 *
 * Colors come from the PetroAI design tokens (src/styles/tokens.css), NOT
 * Telegram's --tg-theme-* vars, so the app is pixel-identical to the approved
 * mockups in both dark and light themes (design-system.md §2).
 *
 * Routes use React.lazy + Suspense for route-level code-splitting
 * (REQ-nfr-performance: ≤300 KB gzip bundle).
 */

import { lazy, Suspense, CSSProperties } from "react";
import { Routes, Route } from "react-router-dom";

import AppShell from "./components/AppShell";
import RoleHintModal from "./components/RoleHintModal";

// ── Shared style tokens (canonical source — reused by page components) ─────────

// Intentional: `styles` is the canonical shared style-token object imported by the
// page components. Co-locating it with the App component trips react-refresh's
// only-export-components heuristic, but these are static tokens (no fast-refresh
// benefit to splitting them into their own module).
// eslint-disable-next-line react-refresh/only-export-components
export const styles = {
  app: {
    minHeight: "100vh",
    backgroundColor: "var(--bg)",
    color: "var(--text)",
    fontFamily: "inherit",
  } as CSSProperties,
  header: {
    padding: "16px",
    borderBottom: "1px solid var(--border)",
    backgroundColor: "var(--surface)",
  } as CSSProperties,
  headerTitle: {
    margin: 0,
    fontSize: "20px",
    fontWeight: 700,
    color: "var(--text)",
  } as CSSProperties,
  headerSubtitle: {
    margin: "4px 0 0",
    fontSize: "13px",
    color: "var(--text-muted)",
  } as CSSProperties,
  main: {
    padding: "16px",
  } as CSSProperties,
  card: {
    borderRadius: "var(--r-md)",
    padding: "16px",
    backgroundColor: "var(--surface)",
    border: "1px solid var(--border)",
    boxShadow: "var(--shadow)",
    marginBottom: "12px",
  } as CSSProperties,
  cardTitle: {
    margin: "0 0 8px",
    fontSize: "15px",
    fontWeight: 600,
    color: "var(--text)",
  } as CSSProperties,
  cardText: {
    margin: 0,
    fontSize: "13px",
    color: "var(--text-muted)",
  } as CSSProperties,
  accentButton: {
    display: "block",
    width: "100%",
    minHeight: "48px",
    padding: "12px 20px",
    borderRadius: "var(--r-md)",
    backgroundColor: "var(--green)",
    color: "var(--green-on)",
    border: "none",
    fontSize: "16px",
    fontWeight: 600,
    cursor: "pointer",
    boxSizing: "border-box" as const,
  } as CSSProperties,
} as const;

// ── Lazy-loaded routes (code-split by route) ───────────────────────────────────

// Landing + tab destinations (unified shell — IMG_0046)
const Home = lazy(() => import("./pages/Home"));
const HowItWorks = lazy(() => import("./pages/HowItWorks"));
const Support = lazy(() => import("./pages/Support"));
const Market = lazy(() => import("./pages/Market"));
const OfferDetail = lazy(() => import("./pages/OfferDetail"));
const News = lazy(() => import("./pages/News"));
const NewsDetail = lazy(() => import("./pages/NewsDetail"));
const Sell = lazy(() => import("./pages/Sell"));
const SellOffer = lazy(() => import("./pages/SellOffer"));
const Profile = lazy(() => import("./pages/Profile"));

const Step1 = lazy(() => import("./pages/wizard/Step1"));
const Step2 = lazy(() => import("./pages/wizard/Step2"));
const Step3 = lazy(() => import("./pages/wizard/Step3"));
const Step4 = lazy(() => import("./pages/wizard/Step4"));
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
        backgroundColor: "var(--bg)",
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
          border: "3px solid var(--border)",
          borderTopColor: "var(--green)",
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
      <RoleHintModal />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Launch screen — the Главный экран landing (design_2 buyer ①) */}
          <Route path="/" element={<AppShell><Home /></AppShell>} />

          {/* Tab destinations (with bottom tab bar) */}
          <Route path="/market" element={<AppShell><Market /></AppShell>} />
          <Route path="/requests" element={<AppShell><MyRequests /></AppShell>} />
          <Route path="/sell" element={<AppShell><Sell /></AppShell>} />
          <Route path="/news" element={<AppShell><News /></AppShell>} />
          <Route path="/profile" element={<AppShell><Profile /></AppShell>} />

          {/* Full-screen flows (no tab bar) */}
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="/support" element={<Support />} />
          <Route path="/market/:id" element={<OfferDetail />} />
          <Route path="/sell/new" element={<SellOffer />} />
          <Route path="/news/:id" element={<NewsDetail />} />
          <Route path="/request/step/1" element={<Step1 />} />
          <Route path="/request/step/2" element={<Step2 />} />
          <Route path="/request/step/3" element={<Step3 />} />
          <Route path="/request/step/4" element={<Step4 />} />
          <Route path="/request/confirm" element={<Confirm />} />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Suspense>
    </div>
  );
}
