import { type HTMLAttributes } from "react";

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

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-b border-border px-5 py-4", className)} {...rest} />;
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
