/**
 * AppShell — the sticky top header (language switcher, top-right) for the five tab
 * destinations. The bottom tab bar is rendered once globally in App (it shows on
 * every screen), so AppShell only owns the header now.
 */

import type { ReactNode } from "react";

import LanguageSwitcher from "./LanguageSwitcher";

const HEADER_HEIGHT = 56; // px — kept in sync with full-height pages (e.g. Home)

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
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
    </>
  );
}
