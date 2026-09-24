import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Badge } from "@/shared/ui";

import type { TechnologistCard } from "../model/types";

import { TechnologistAvatar } from "./TechnologistAvatar";
import { TechnologistRating } from "./TechnologistRating";

/**
 * An expert in the catalog — a LINK, like `PublicCompanyTile`, so a crawler
 * sees the catalog's children. `to` is overridable for the cabinet surfaces
 * that open the same card in another context.
 */
export function TechnologistTile({
  card,
  to = `/technologists/${card.id}`,
}: {
  card: TechnologistCard;
  to?: string;
}) {
  const { t } = useTranslation();
  const place = [card.city, card.country].filter(Boolean).join(", ");

  return (
    <Link
      to={to}
      className="group flex h-full min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-brand-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
    >
      <TechnologistSummary card={card} />

      <div className="flex flex-wrap gap-1.5">
        {card.processes.slice(0, 4).map((p) => (
          <Badge key={p} tone="brand">
            {t(`technologists.process.${p}`)}
          </Badge>
        ))}
        {card.materials.slice(0, 5).map((m) => (
          <Badge key={m}>{m}</Badge>
        ))}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3 text-xs">
        <span className="truncate text-text-muted">{place}</span>
        <Badge variant="verified" className="shrink-0">
          {t("technologists.profileVerified")}
        </Badge>
      </div>
    </Link>
  );
}

/** Portrait, name, title, experience, rating — the head of every expert card. */
export function TechnologistSummary({ card }: { card: TechnologistCard }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-w-0 items-start gap-3">
      <TechnologistAvatar photoUrl={card.photo_url} />
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-semibold text-text">
          {card.full_name ?? t("technologists.untitled")}
        </h3>
        {card.title ? <p className="truncate text-xs text-text-muted">{card.title}</p> : null}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          {card.years_experience != null ? (
            <span className="num text-xs text-text-muted">
              {t("technologists.years", { count: card.years_experience })}
            </span>
          ) : null}
          <TechnologistRating avg={card.rating_avg} count={card.rating_count} />
        </div>
      </div>
    </div>
  );
}
