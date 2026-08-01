import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

type AlertTone = "info" | "success" | "warning" | "danger";

interface AlertProps {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
  "data-testid"?: string;
}

/*
 * `/10`, not the `/8` these shipped with. A BARE opacity modifier has to be a
 * value from `theme.opacity`, which steps by 5 — `bg-info/8` compiles to no rule
 * at all, so every Alert has been drawing its border and its dot with no tinted
 * fill behind them since it was written. (The token colours themselves could not
 * take an alpha at all until `tailwind.config.ts` grew `token()`; this is the
 * second half of the same silent failure.)
 */
const tones: Record<AlertTone, string> = {
  info: "bg-info/10 border-info/30 text-text",
  success: "bg-success/10 border-success/30 text-text",
  warning: "bg-warning/10 border-warning/30 text-text",
  danger: "bg-danger/10 border-danger/30 text-text",
};

const dot: Record<AlertTone, string> = {
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

export function Alert({
  tone = "info",
  title,
  children,
  action,
  className,
  "data-testid": testId,
}: AlertProps) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded-md border px-4 py-3", tones[tone], className)}
      data-testid={testId}
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
