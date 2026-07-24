import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

type AlertTone = "info" | "success" | "warning" | "danger";

interface AlertProps {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}

const tones: Record<AlertTone, string> = {
  info: "bg-info/8 border-info/30 text-text",
  success: "bg-success/8 border-success/30 text-text",
  warning: "bg-warning/8 border-warning/30 text-text",
  danger: "bg-danger/8 border-danger/30 text-text",
};

const dot: Record<AlertTone, string> = {
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

export function Alert({ tone = "info", title, children, action, className }: AlertProps) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded-md border px-4 py-3", tones[tone], className)}
    >
      <div className="flex items-start gap-3">
        <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", dot[tone])} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          {title ? <p className="text-sm font-semibold">{title}</p> : null}
          {children ? <div className="mt-0.5 text-sm text-text-muted">{children}</div> : null}
          {action ? <div className="mt-2">{action}</div> : null}
        </div>
      </div>
    </div>
  );
}
