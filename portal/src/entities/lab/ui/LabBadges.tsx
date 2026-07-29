import { useTranslation } from "react-i18next";

import { Badge, FlaskIcon } from "@/shared/ui";

interface LabBadgesProps {
  hasLabPassport: boolean;
  labVerified: boolean;
  className?: string;
}

/**
 * The two laboratory badges — and they are NOT the same claim.
 *
 * "Lab passport" means a PDF is attached; anyone can earn it by uploading one.
 * "Laboratory Verified" means we sent the material to a partner laboratory
 * ourselves. Only the second is independent, so only the second gets the gold
 * `lab-verified` variant, and a verified offer shows only that one — printing
 * both would read as two separate endorsements of the same document.
 */
export function LabBadges({ hasLabPassport, labVerified, className }: LabBadgesProps) {
  const { t } = useTranslation();
  if (!hasLabPassport && !labVerified) return null;

  return (
    <div className={className}>
      <div className="flex flex-wrap gap-1.5">
        {labVerified ? (
          <Badge variant="lab-verified">{t("lab.badge.verified")}</Badge>
        ) : (
          <Badge tone="neutral" icon={<FlaskIcon />}>
            {t("lab.badge.passport")}
          </Badge>
        )}
      </div>
    </div>
  );
}
