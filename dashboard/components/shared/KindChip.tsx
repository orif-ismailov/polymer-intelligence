"use client";

/**
 * KindChip — signal/request kind badge.
 * Uses kind token classes only (no hardcoded hex). UI-SPEC §Color / Kind tokens.
 */

const KIND_CLASSES: Record<string, string> = {
  buy_request: "text-kind-buy-request border-kind-buy-request",
  sell_offer: "text-kind-sell-offer border-kind-sell-offer",
  deal: "text-kind-deal border-kind-deal",
  price_quote: "text-kind-price-quote border-kind-price-quote",
  news: "text-kind-news border-kind-news",
};

const KIND_LABELS: Record<string, string> = {
  buy_request: "BUYER",
  sell_offer: "SELLER",
  deal: "DEAL",
  price_quote: "PRICE",
  news: "NEWS",
};

interface KindChipProps {
  kind: string;
  className?: string;
}

export function KindChip({ kind, className = "" }: KindChipProps) {
  const colorClasses = KIND_CLASSES[kind] ?? "text-foreground-muted border-foreground-muted";
  const label = KIND_LABELS[kind] ?? kind.toUpperCase();

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${colorClasses} ${className}`}
    >
      {label}
    </span>
  );
}
