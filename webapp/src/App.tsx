/**
 * IMEX AI — Telegram Web App router shell.
 *
 * Colors come from the IMEX AI design tokens (src/styles/tokens.css), NOT
 * Telegram's --tg-theme-* vars, so the app is pixel-identical to the approved
 * mockups in both dark and light themes (design-system.md §2).
 *
 * Routes use React.lazy + Suspense for route-level code-splitting
 * (REQ-nfr-performance: ≤300 KB gzip bundle).
 */

import { lazy, Suspense, useEffect, CSSProperties } from "react";
import { Routes, Route, Outlet } from "react-router-dom";

import AppShell from "./components/AppShell";
import BottomTabBar from "./components/BottomTabBar";
import RequireAuth from "./components/RequireAuth";
import RoleHintModal from "./components/RoleHintModal";
import TopNav from "./components/TopNav";
import { useIsDesktop } from "./hooks/useIsDesktop";
import { useAuthStore } from "./store/authStore";

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

// Public marketing landing (IMEX AI) — rendered at "/" outside the app chrome.
const Landing = lazy(() => import("./pages/Landing"));
// Tab destinations + flows
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

// ── App layout for the functional (non-landing) routes ─────────────────────────
// Owns the responsive chrome: desktop TopNav ↔ mobile BottomTabBar, a centered
// max-width container on desktop, and the browser auth gate (RequireAuth). Mini App
// is always authed so the gate is a no-op there.

function AppLayout() {
  const isDesktop = useIsDesktop();
  const authed = useAuthStore((s) => s.status === "authed");

  return (
    <div style={styles.app}>
      <RoleHintModal />
      {isDesktop && authed && <TopNav />}
      <div
        className={isDesktop ? "imex-app-container" : undefined}
        style={{
          // Reserve space for the fixed mobile BottomTabBar (only shown on mobile+authed).
          paddingBottom: !isDesktop && authed ? "calc(72px + env(safe-area-inset-bottom))" : undefined,
        }}
      >
        <RequireAuth>
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </RequireAuth>
      </div>
      {!isDesktop && authed && <BottomTabBar />}
    </div>
  );
}

// ── App route table ────────────────────────────────────────────────────────────

export default function App() {
  const bootstrap = useAuthStore((s) => s.bootstrap);
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return (
    <Routes>
      {/* Public marketing landing — full-bleed, its own chrome, no auth gate. */}
      <Route
        path="/"
        element={
          <Suspense fallback={<PageLoader />}>
            <Landing />
          </Suspense>
        }
      />

      {/* Functional app — behind the responsive chrome + browser auth gate. */}
      <Route element={<AppLayout />}>
        {/* Tab destinations (mobile compact header via AppShell) */}
        <Route path="/market" element={<AppShell><Market /></AppShell>} />
        <Route path="/requests" element={<AppShell><MyRequests /></AppShell>} />
        <Route path="/sell" element={<AppShell><Sell /></AppShell>} />
        <Route path="/news" element={<AppShell><News /></AppShell>} />
        <Route path="/profile" element={<AppShell><Profile /></AppShell>} />

        {/* Full-screen flows */}
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
      </Route>
    </Routes>
  );
}
