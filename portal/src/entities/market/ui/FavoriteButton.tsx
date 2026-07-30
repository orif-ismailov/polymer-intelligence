import { Heart } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib";

import { useToggleFavorite } from "../model/hooks";

interface FavoriteButtonProps {
  offerId: number;
  isFavorite: boolean;
  className?: string;
}

/**
 * The heart on a market card.
 *
 * Sits INSIDE a card that is itself a button, so it stops propagation — tapping
 * the heart must not also open the offer. `aria-pressed` carries the state for
 * assistive tech; the fill alone would be invisible to it.
 */
export function FavoriteButton({ offerId, isFavorite, className }: FavoriteButtonProps) {
  const { t } = useTranslation();
  const toggle = useToggleFavorite();

  return (
    <button
      type="button"
      aria-pressed={isFavorite}
      aria-label={t(isFavorite ? "market.unfavorite" : "market.favorite")}
      title={t(isFavorite ? "market.unfavorite" : "market.favorite")}
      onClick={(event) => {
        event.stopPropagation();
        event.preventDefault();
        toggle.mutate({ offerId, next: !isFavorite });
      }}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface/90 backdrop-blur transition-colors",
        isFavorite ? "text-danger" : "text-text-subtle hover:text-text",
        className,
      )}
    >
      <Heart
        size={16}
        strokeWidth={1.75}
        aria-hidden="true"
        className={isFavorite ? "fill-current" : undefined}
      />
    </button>
  );
}
