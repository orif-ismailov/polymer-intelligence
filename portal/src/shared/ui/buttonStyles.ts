import { cn } from "@/shared/lib";

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-bg disabled:pointer-events-none disabled:opacity-50 select-none";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-brand text-brand-fg hover:bg-brand/90 active:bg-brand/95",
  secondary: "bg-surface-2 text-text hover:bg-surface-2/70 border border-border",
  outline: "border border-border-strong bg-transparent text-text hover:bg-surface-2",
  ghost: "bg-transparent text-text hover:bg-surface-2",
  danger: "bg-danger text-white hover:bg-danger/90",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

/** Compose the button class string — shared by <Button> and <LinkButton>. */
export function buttonClasses(
  options: {
    variant?: ButtonVariant;
    size?: ButtonSize;
    fullWidth?: boolean;
    className?: string;
  } = {},
): string {
  const { variant = "primary", size = "md", fullWidth = false, className } = options;
  return cn(base, variants[variant], sizes[size], fullWidth && "w-full", className);
}
