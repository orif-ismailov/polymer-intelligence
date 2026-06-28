/**
 * AppShell — page chrome for the five tab destinations: themed canvas + bottom
 * space reserved for the fixed BottomTabBar. Full-screen flows (wizard, request
 * detail) render WITHOUT this shell.
 */

import type { ReactNode } from "react";

import BottomTabBar from "./BottomTabBar";

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
      {children}
      <BottomTabBar />
    </div>
  );
}
