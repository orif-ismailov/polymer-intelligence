import { Menu } from "lucide-react";
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
    // `z-30` — above the rail, which starts under this bar and must scroll
    // beneath it rather than over it.
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
      {/* Edge to edge, so the lockup sits in the actual corner. It used to be
          centred in the same `max-w-6xl` as the content, which put it 384px
          adrift on a 1920 screen and was half of why the app read as a page
          floating in a void rather than as a frame. */}
      <div className="flex h-14 items-center gap-3 px-4 lg:px-6">
        {/* This opened the drawer while announcing itself as "Home". */}
        <button
          type="button"
          aria-label={t("nav.openMenu")}
          aria-controls="portal-nav-drawer"
          onClick={onOpenMenu}
          className="rounded-md p-2 text-text-muted transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand md:hidden"
        >
          <Menu size={20} strokeWidth={1.75} aria-hidden="true" />
        </button>

        {/* The lockup goes to the public home from everywhere it is drawn — in
            the cabinet too. The cabinet home has its own nav entry (and the
            phone bottom bar's first slot); the brand mark is the way out to the
            marketplace. */}
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
