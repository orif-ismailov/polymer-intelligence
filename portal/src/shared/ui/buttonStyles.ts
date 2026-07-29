import { cn } from "@/shared/lib";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "danger"
  | "gold";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-bg disabled:pointer-events-none select-none";

/*
 * Disabled is a *neutral* treatment rather than an opacity fade: the brand fill
 * carries a dark label (--brand-fg), and fading that pair over a dark page turned
 * the label into dark-on-dark mud. Dropping to the raised surface with subtle
 * text keeps a disabled CTA readable in both themes.
 */
const disabledState =
  "disabled:bg-surface-2 disabled:text-text-subtle disabled:border-border disabled:shadow-none " +
  "disabled:brightness-100";

const variants: Record<ButtonVariant, string> = {
  // The mockups' hero CTA: solid neon green, dark label, lighting up on hover.
  primary: "bg-brand text-brand-fg hover:brightness-110 hover:shadow-glow active:brightness-95",
  secondary: "bg-surface-2 text-text hover:bg-surface-2/70 border border-border",
  // Sits next to `primary` throughout the mockups ("Связаться с продавцом").
  outline:
    "border border-border-strong bg-transparent text-text hover:border-brand-line hover:bg-brand-soft",
  ghost: "bg-transparent text-text hover:bg-surface-2",
  danger: "bg-danger text-danger-fg hover:brightness-110",
  /*
   * The publish moment. The mockups switch the CTA from neon green to gold at the
   * last step of the offer and RFQ wizards ("Опубликовать заявку" / "Опубликовать
   * товар") — the one action that makes something public gets its own colour.
   * Reuses the already-AA-tested --accent-gold / --accent-gold-fg pair.
   */
  gold: "bg-gold text-gold-fg hover:brightness-110 hover:shadow-glow active:brightness-95",
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
  return cn(base, variants[variant], disabledState, sizes[size], fullWidth && "w-full", className);
}
