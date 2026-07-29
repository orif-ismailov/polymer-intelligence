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
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M12 20.3l-1.45-1.32C5.4 14.36 2 11.28 2 7.5 2 4.42 4.42 2 7.5 2c1.74 0 3.41.81 4.5 2.09C13.09 2.81 14.76 2 16.5 2 19.58 2 22 4.42 22 7.5c0 3.78-3.4 6.86-8.55 11.49L12 20.3z"
          fill={isFavorite ? "currentColor" : "none"}
          stroke="currentColor"
          strokeWidth="1.6"
        />
      </svg>
    </button>
  );
}
