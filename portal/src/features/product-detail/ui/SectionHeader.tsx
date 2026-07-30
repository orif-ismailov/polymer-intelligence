import { type ReactNode } from "react";

import { cn } from "@/shared/lib";
import { InfoIcon } from "@/shared/ui";

interface SectionHeaderProps {
  title: string;
  icon?: ReactNode;
  /** Info tip shown next to the title (mockup's «(i)»). */
  hint?: string;
  action?: ReactNode;
  className?: string;
}

/** Section title used on every product-detail block under the tabs. */
export function SectionHeader({ title, icon, hint, action, className }: SectionHeaderProps) {
  return (
    <div className={cn("mb-3 flex items-center gap-2", className)}>
      {icon ? <span className="shrink-0 text-gold">{icon}</span> : null}
      <h3 className="min-w-0 flex-1 text-sm font-semibold text-text">{title}</h3>
      {hint ? (
        <span className="shrink-0 text-text-subtle" title={hint}>
          <InfoIcon size={14} />
        </span>
      ) : null}
      {action}
    </div>
  );
}
