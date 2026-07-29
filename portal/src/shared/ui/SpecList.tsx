import { type ReactNode } from "react";

import { cn } from "@/shared/lib";

interface SpecListProps {
  columns?: 1 | 2;
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
 * компании" / request-summary grid. A semantic `<dl>`, which the ten hand-rolled
 * copies of this were — two of them (market offer detail, request detail) byte
 * for byte the same local component.
 */
export function SpecList({ columns = 2, className, children }: SpecListProps) {
  return (
    <dl
      className={cn(
        "grid gap-x-4 gap-y-3 text-sm",
        columns === 2 ? "sm:grid-cols-2" : "grid-cols-1",
        className,
      )}
      data-testid="ui-spec-list"
    >
      {children}
    </dl>
  );
}

export function SpecItem({ label, value, numeric = false, span = 1 }: SpecItemProps) {
  return (
    <div className={cn("min-w-0", span === 2 && "sm:col-span-2")}>
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className={cn("mt-0.5 font-medium text-text", numeric && "num")}>{value}</dd>
    </div>
  );
}
