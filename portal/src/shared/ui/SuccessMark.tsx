import { cn } from "@/shared/lib";

export type SuccessMarkSize = "md" | "lg";

interface SuccessMarkProps {
  size?: SuccessMarkSize;
  className?: string;
  "data-testid"?: string;
}

const sizes: Record<SuccessMarkSize, { box: string; stroke: number; tick: string }> = {
  md: { box: "h-16 w-16", stroke: 2.5, tick: "M6.2 12.2 10.2 16.2 17.8 8" },
  lg: { box: "h-28 w-28", stroke: 2, tick: "M6.2 12.2 10.2 16.2 17.8 8" },
};

/**
 * The big ringed tick the mockups celebrate with — the «Компания успешно
 * проверена» panel and the «Регистрация завершена!» sheet.
 *
 * Drawn rather than composed from CheckIcon + a border so the ring weight scales
 * with the mark; the glow is the same `--brand-glow` token the CTAs use.
 */
export function SuccessMark({
  size = "md",
  className,
  "data-testid": testId,
}: SuccessMarkProps) {
  const spec = sizes[size];
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full text-brand shadow-glow",
        spec.box,
        className,
      )}
      data-testid={testId}
    >
      <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="10.6" stroke="currentColor" strokeWidth={spec.stroke} />
        <path
          d={spec.tick}
          stroke="currentColor"
          strokeWidth={spec.stroke + 0.4}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
