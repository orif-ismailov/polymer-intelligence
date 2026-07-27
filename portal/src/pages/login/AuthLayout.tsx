import { type ReactNode } from "react";

import { BrandLogo } from "@/shared/ui";

import { LanguageMenu } from "./LanguageMenu";

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

/** Centered card layout shared by the login + OTP screens. */
export function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <header className="flex items-center justify-between px-4 py-4">
        <BrandLogo withTagline />
        <LanguageMenu />
      </header>

      <main className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-md">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-semibold text-text">{title}</h1>
            <p className="mt-2 text-sm text-text-muted">{subtitle}</p>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
