"use client";

/**
 * UrgencyChip — urgency level badge with icon + color.
 * Color alone NEVER conveys urgency — icon + color per UI-SPEC Accessibility.
 * Uses token classes only (no hardcoded hex).
 */

import { Flame, Users, Download, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";

const URGENCY_CONFIG: Record<string, { labelKey: string; colorClass: string; Icon: LucideIcon }> = {
  high: {
    labelKey: "urgency.high",
    colorClass: "text-urgency-high border-urgency-high",
    Icon: Flame,
  },
  medium: {
    labelKey: "urgency.medium",
    colorClass: "text-urgency-medium border-urgency-medium",
    Icon: Users,
  },
  low: {
    labelKey: "urgency.low",
    colorClass: "text-urgency-low border-urgency-low",
    Icon: Download,
  },
};

interface UrgencyChipProps {
  urgency: string;
  className?: string;
}

export function UrgencyChip({ urgency, className = "" }: UrgencyChipProps) {
  const t = useTranslations("common");
  const config = URGENCY_CONFIG[urgency];
  if (!config) {
    return (
      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold text-foreground-muted border-foreground-muted ${className}`}>
        {urgency}
      </span>
    );
  }

  const { labelKey, colorClass, Icon } = config;
  const label = t(labelKey);

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${colorClass} ${className}`}
      aria-label={t("urgencyAriaLabel", { label })}
    >
      <Icon size={10} className="flex-shrink-0" aria-hidden="true" />
      {label}
    </span>
  );
}
