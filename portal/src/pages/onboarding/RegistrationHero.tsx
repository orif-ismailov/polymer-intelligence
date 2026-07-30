import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib";

/**
 * Capability chips orbiting the trust shield. Positions are percentages of the
 * box and are deliberately fixed — the arrangement is part of the composition,
 * not decoration to be shuffled.
 */
const CHIPS = [
  { key: "aiMatching", className: "left-0 top-[16%]" },
  { key: "verifiedCompany", className: "right-0 top-[10%]" },
  { key: "tradeFinance", className: "left-0 top-[46%]" },
  { key: "secureDeals", className: "right-0 top-[44%]" },
  { key: "logistics", className: "left-[8%] bottom-[6%]" },
  { key: "governmentApi", className: "right-0 bottom-[8%]" },
] as const;

interface RegistrationHeroProps {
  className?: string;
}

/** The shield-and-orbit illustration that heads the registration entry sheet. */
export function RegistrationHero({ className }: RegistrationHeroProps) {
  const { t } = useTranslation();

  return (
    <div className={cn("relative mx-auto w-full max-w-sm", className)}>
      <svg
        viewBox="0 0 320 220"
        className="w-full"
        fill="none"
        role="img"
        aria-label={t("onboarding.heroAlt")}
      >
        <defs>
          <linearGradient id="onb-shield" x1="160" y1="34" x2="160" y2="186" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="var(--brand)" stopOpacity="0.32" />
            <stop offset="1" stopColor="var(--brand)" stopOpacity="0.05" />
          </linearGradient>
          <radialGradient id="onb-glow" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stopColor="var(--brand)" stopOpacity="0.4" />
            <stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
          </radialGradient>
        </defs>

        <ellipse cx="160" cy="112" rx="96" ry="82" fill="url(#onb-glow)" />

        {/* Orbit: one ring drawn twice, so the shield reads as sitting inside it. */}
        <ellipse
          cx="160"
          cy="120"
          rx="104"
          ry="34"
          stroke="var(--brand)"
          strokeOpacity="0.55"
          strokeWidth="1.5"
          transform="rotate(-12 160 120)"
        />
        <circle cx="58" cy="112" r="3.5" fill="var(--brand)" />
        <circle cx="262" cy="128" r="3" fill="var(--brand)" />
        <circle cx="120" cy="152" r="2" fill="var(--brand)" opacity="0.7" />
        <circle cx="212" cy="80" r="2" fill="var(--brand)" opacity="0.7" />

        {/* Shield */}
        <path
          d="M160 30 96 54v54c0 34 26 64 64 78 38-14 64-44 64-78V54l-64-24Z"
          fill="url(#onb-shield)"
          stroke="var(--brand)"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <path
          d="m133 110 20 20 40-44"
          stroke="var(--brand)"
          strokeWidth="11"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* The near half of the orbit, redrawn ON TOP: the ring passing behind
            the shield's shoulders and in front of its foot is what reads as
            depth. One ellipse alone just looks like a line stopping at an edge. */}
        <path
          d="M56 120a104 34 -12 0 0 208 0"
          stroke="var(--brand)"
          strokeWidth="1.5"
          strokeOpacity="0.9"
          fill="none"
          transform="rotate(-12 160 120)"
        />
      </svg>

      {CHIPS.map((chip) => (
        <span
          key={chip.key}
          className={cn(
            "absolute whitespace-nowrap rounded-md border border-border bg-surface px-2.5 py-1.5 text-[11px] font-medium text-text shadow-sm",
            chip.className,
          )}
        >
          {t(`onboarding.chips.${chip.key}`)}
        </span>
      ))}
    </div>
  );
}
