/**
 * AppShell — page chrome for the five tab destinations: a sticky top header with the
 * language switcher (top-right, per design_2), the themed canvas, and bottom space
 * reserved for the fixed BottomTabBar. Full-screen flows (wizard, request detail,
 * how-it-works, support) render WITHOUT this shell.
 */

import type { ReactNode } from "react";

import BottomTabBar from "./BottomTabBar";
import LanguageSwitcher from "./LanguageSwitcher";

const HEADER_HEIGHT = 56; // px — kept in sync with full-height pages (e.g. Home)

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        paddingBottom: "calc(72px + env(safe-area-inset-bottom))",
      }}
    >
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 40,
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          height: `${HEADER_HEIGHT}px`,
          padding: "0 16px",
          background: "var(--bg)",
        }}
      >
        <LanguageSwitcher />
      </header>

      {children}
      <BottomTabBar />
    </div>
  );
}
