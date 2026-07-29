import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, icon, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      {icon ? <div className="mb-3 text-text-subtle">{icon}</div> : null}
      <h3 className="text-base font-semibold text-text">{title}</h3>
      {description ? <p className="mt-1 max-w-sm text-sm text-text-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
