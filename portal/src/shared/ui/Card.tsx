import { type HTMLAttributes, type ReactNode } from "react";

import { cn } from "@/shared/lib";

export type CardVariant = "default" | "accent";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** `accent` draws the thin brand outline the mockups use on module cards. */
  variant?: CardVariant;
}

const cardVariants: Record<CardVariant, string> = {
  default: "border-border",
  accent: "border-brand-line",
};

export function Card({ variant = "default", className, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-surface shadow-sm",
        cardVariants[variant],
        className,
      )}
      {...rest}
    />
  );
}

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  /** Glyph before the title — the mockups head most sections with one. */
  icon?: ReactNode;
  /** Right-aligned slot: a status badge, or a "Смотреть все" link. */
  action?: ReactNode;
}

/**
 * With `action` (or `icon`) this renders the `flex items-center justify-between`
 * shape that a dozen call sites were writing by hand; without them it stays the
 * plain block it always was, so existing headers are untouched.
 */
export function CardHeader({ icon, action, className, children, ...rest }: CardHeaderProps) {
  if (!icon && !action) {
    return (
      <div className={cn("border-b border-border px-5 py-4", className)} {...rest}>
        {children}
      </div>
    );
  }
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 border-b border-border px-5 py-4",
        className,
      )}
      {...rest}
    >
      <div className="flex min-w-0 items-center gap-2">
        {icon ? <span className="shrink-0 text-brand">{icon}</span> : null}
        <div className="min-w-0">{children}</div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-base font-semibold text-text", className)} {...rest} />;
}

export function CardDescription({ className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("mt-1 text-sm text-text-muted", className)} {...rest} />;
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...rest} />;
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex items-center gap-3 border-t border-border px-5 py-4", className)}
      {...rest}
    />
  );
}
