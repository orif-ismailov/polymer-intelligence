"use client";

/**
 * KindChip — signal/request kind badge.
 * Uses kind token classes only (no hardcoded hex). UI-SPEC §Color / Kind tokens.
 */

import { useTranslations } from "next-intl";

const KIND_CLASSES: Record<string, string> = {
  buy_request: "text-kind-buy-request border-kind-buy-request",
  sell_offer: "text-kind-sell-offer border-kind-sell-offer",
  deal: "text-kind-deal border-kind-deal",
  price_quote: "text-kind-price-quote border-kind-price-quote",
  news: "text-kind-news border-kind-news",
};

const KIND_KEYS: Record<string, string> = {
  buy_request: "kind.buy_request",
  sell_offer: "kind.sell_offer",
  deal: "kind.deal",
  price_quote: "kind.price_quote",
  news: "kind.news",
};

interface KindChipProps {
  kind: string;
  className?: string;
}

export function KindChip({ kind, className = "" }: KindChipProps) {
  const t = useTranslations("common");
  const colorClasses = KIND_CLASSES[kind] ?? "text-foreground-muted border-foreground-muted";
  const labelKey = KIND_KEYS[kind];
  const label = labelKey ? t(labelKey) : kind.toUpperCase();

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${colorClasses} ${className}`}
    >
      {label}
    </span>
  );
}
