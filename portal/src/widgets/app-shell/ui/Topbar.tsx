import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { NotificationBell } from "@/features/notification-center";
import { CompanySwitcher } from "@/features/switch-company";
import { BrandLogo } from "@/shared/ui";

interface TopbarProps {
  onOpenMenu: () => void;
}

export function Topbar({ onOpenMenu }: TopbarProps) {
  const { t } = useTranslation();
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
        {/* This opened the drawer while announcing itself as "Home". */}
        <button
          type="button"
          aria-label={t("nav.openMenu")}
          aria-controls="portal-nav-drawer"
          onClick={onOpenMenu}
          className="rounded-md p-2 text-text-muted transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand md:hidden"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>

        <Link to="/" aria-label={t("common.appName")} className="flex items-center">
          <BrandLogo className="[&>span:last-child]:hidden sm:[&>span:last-child]:block" />
        </Link>

        <div className="ml-auto flex items-center gap-3">
          <NotificationBell />
          <CompanySwitcher />
        </div>
      </div>
    </header>
  );
}
