import { useTranslation } from "react-i18next";

import { Badge } from "@/shared/ui";

/**
 * Confirmed business roles of the company behind an offer.
 *
 * The glyphs come from the mockups. They are decoration, not information: the
 * label carries the meaning, so the emoji is aria-hidden and a screen reader
 * hears "Производитель", not "factory emoji".
 *
 * The backend sends CONFIRMED roles only, so anything rendered here has been
 * checked by staff — that is the whole point of the badge.
 */
const GLYPHS: Record<string, string> = {
  manufacturer: "🏭",
  distributor: "✅",
  importer: "📦",
  trader: "🌍",
  laboratory: "🧪",
  logistics_provider: "🚚",
  insurance_provider: "🛡",
};

interface BusinessRoleBadgesProps {
  roles: string[];
  className?: string;
  /** Cap the number shown; the rest collapse into a "+N". */
  max?: number;
}

export function BusinessRoleBadges({ roles, className, max }: BusinessRoleBadgesProps) {
  const { t } = useTranslation();
  if (roles.length === 0) return null;

  const shown = max ? roles.slice(0, max) : roles;
  const hidden = roles.length - shown.length;

  return (
    <div className={className}>
      <div className="flex flex-wrap gap-1.5">
        {shown.map((role) => (
          <Badge key={role} tone="neutral">
            <span aria-hidden="true">{GLYPHS[role] ?? "•"}</span> {t(`businessRole.${role}`)}
          </Badge>
        ))}
        {hidden > 0 ? <Badge tone="neutral">+{hidden}</Badge> : null}
      </div>
    </div>
  );
}
