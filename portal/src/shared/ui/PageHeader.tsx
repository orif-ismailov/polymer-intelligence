import { type ReactNode } from "react";

import { Link } from "react-router-dom";

import { cn } from "@/shared/lib";

import { ChevronLeftIcon } from "./icons";

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Status pill shown inline beside the title (the mockups put it there, not below). */
  badge?: ReactNode;
  /** Renders the mockups' "‹ Назад" affordance above the title. */
  backTo?: string;
  /** Caller supplies the string — `shared/ui` never imports i18n. */
  backLabel?: string;
  /** Right-aligned CTA slot. */
  actions?: ReactNode;
  className?: string;
}

/**
 * The page chrome every screen opens with: optional back link, an `<h1>` with an
 * optional inline badge, an optional subtitle, and a right-hand action slot.
 *
 * This exists because the same three lines of Tailwind were retyped in 28 files,
 * which is why the screens drifted from each other and from the mockups. The type
 * ramp lives here (see docs/design-system.md Part II §P6) so a page never picks a
 * font size for its own header again.
 *
 * The `<h1>` is load-bearing: the e2e flows locate screens with
 * `getByRole("heading", { level: 1 })`.
 */
export function PageHeader({
  title,
  subtitle,
  badge,
  backTo,
  backLabel,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn(className)} data-testid="ui-page-header">
      {backTo ? (
        <Link
          to={backTo}
          className="mb-2 inline-flex items-center gap-1 rounded-sm text-sm text-text-muted transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronLeftIcon size={14} />
          {backLabel}
        </Link>
      ) : null}

      <div className={cn(actions && "flex items-start justify-between gap-4")}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-text">{title}</h1>
            {badge}
          </div>
          {subtitle ? <p className="mt-1 text-sm text-text-muted">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}
