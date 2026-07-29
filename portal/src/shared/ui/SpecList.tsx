import { createContext, useContext, type ReactNode } from "react";

import { cn } from "@/shared/lib";

/**
 * `stacked` is the sheets' summary block — label above value, used where the
 * grid IS the content (contract data, company information, request parameters).
 * `inline` is the compact `label: value` line the sheets use inside list cards,
 * where the grid is secondary to a title and a status badge.
 */
export type SpecListVariant = "stacked" | "inline";

const VariantContext = createContext<SpecListVariant>("stacked");

interface SpecListProps {
  columns?: 1 | 2;
  variant?: SpecListVariant;
  className?: string;
  children: ReactNode;
}

interface SpecItemProps {
  label: ReactNode;
  value: ReactNode;
  /** Figures compared down a column get tabular numerals. */
  numeric?: boolean;
  /** Let a long value (an address, a description) take the whole row. */
  span?: 1 | 2;
}

/**
 * The key/value block the mockups use for every "Данные договора" / "Информация о
 * компании" / request-summary grid, and for the compact fact lines inside list
 * cards. Ten call sites had hand-rolled one of these two shapes — two of them
 * (market offer detail, request detail) byte for byte the same local component.
 *
 * The variant travels by context rather than as a prop on every item: a list is
 * one shape throughout, and threading it through each child is how call sites
 * end up with a stray mismatched row.
 */
export function SpecList({
  columns = 2,
  variant = "stacked",
  className,
  children,
}: SpecListProps) {
  return (
    <VariantContext.Provider value={variant}>
      <dl
        className={cn(
          "grid text-sm",
          variant === "stacked" ? "gap-x-4 gap-y-3" : "gap-x-4 gap-y-1",
          columns === 2 ? "sm:grid-cols-2" : "grid-cols-1",
          className,
        )}
        data-testid="ui-spec-list"
      >
        {children}
      </dl>
    </VariantContext.Provider>
  );
}

export function SpecItem({ label, value, numeric = false, span = 1 }: SpecItemProps) {
  const variant = useContext(VariantContext);

  if (variant === "inline") {
    return (
      <div className={cn("flex min-w-0 gap-2", span === 2 && "sm:col-span-2")}>
        <dt className="shrink-0 text-text-muted">{label}:</dt>
        <dd className={cn("min-w-0 truncate text-text", numeric && "num")}>{value}</dd>
      </div>
    );
  }

  return (
    <div className={cn("min-w-0", span === 2 && "sm:col-span-2")}>
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className={cn("mt-0.5 font-medium text-text", numeric && "num")}>{value}</dd>
    </div>
  );
}
