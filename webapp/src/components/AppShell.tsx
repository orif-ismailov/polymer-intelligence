/**
 * AppShell — the sticky top header for the five tab destinations: the PetroAI
 * wordmark on the left, the language switcher on the right (one line). The bottom
 * tab bar is rendered once globally in App (shows on every screen), so AppShell
 * only owns the header.
 */

import type { ReactNode } from "react";
import { Sparkles } from "lucide-react";

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
          justifyContent: "space-between",
          gap: "12px",
          height: `${HEADER_HEIGHT}px`,
          padding: "0 16px",
          background: "var(--bg)",
        }}
      >
        {/* Brand wordmark */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
          <span
            style={{
              width: "28px",
              height: "28px",
              borderRadius: "var(--r-sm)",
              background: "var(--green)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flex: "0 0 auto",
            }}
          >
            <Sparkles size={16} color="var(--green-on)" />
          </span>
          <span style={{ lineHeight: 1 }}>
            <span style={{ display: "block", fontSize: "15px", fontWeight: 700, color: "var(--text)", lineHeight: 1 }}>
              PetroAI
            </span>
            <span
              style={{
                display: "block",
                fontSize: "9px",
                fontWeight: 600,
                letterSpacing: "0.08em",
                color: "var(--text-muted)",
                marginTop: "2px",
              }}
            >
              AI MARKETPLACE
            </span>
          </span>
        </div>

        <LanguageSwitcher />
      </header>
      {children}
    </>
  );
}
