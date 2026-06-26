import type { ReactNode } from "react";

/**
 * Required root layout for the next-intl /[locale]/ setup. It only passes
 * children through — the real <html>/<body>, fonts, and providers live in
 * app/[locale]/layout.tsx (which is the effective root for every route).
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
