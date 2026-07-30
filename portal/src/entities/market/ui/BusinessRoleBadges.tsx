import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import {
  Badge,
  BoxIcon,
  FactoryIcon,
  FlaskIcon,
  TraderIcon,
  ShieldIcon,
  SupplierIcon,
  TruckIcon,
} from "@/shared/ui";

/**
 * Confirmed business roles of the company behind an offer.
 *
 * Glyphs are decorative; the translated label carries the meaning.
 * The backend sends CONFIRMED roles only — anything rendered here has been
 * checked by staff.
 */
const GLYPHS: Record<string, ReactNode> = {
  manufacturer: <FactoryIcon size={12} />,
  distributor: <SupplierIcon size={12} />,
  importer: <BoxIcon size={12} />,
  trader: <TraderIcon size={12} />,
  laboratory: <FlaskIcon size={12} />,
  logistics_provider: <TruckIcon size={12} />,
  insurance_provider: <ShieldIcon size={12} />,
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
          <Badge key={role} tone="neutral" icon={GLYPHS[role]}>
            {t(`businessRole.${role}`)}
          </Badge>
        ))}
        {hidden > 0 ? <Badge tone="neutral">+{hidden}</Badge> : null}
      </div>
    </div>
  );
}
