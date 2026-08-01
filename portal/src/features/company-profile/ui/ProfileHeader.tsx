import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { BusinessRoleBadges } from "@/entities/market";
import { coerceLang } from "@/shared/i18n";
import { countryName, formatDate } from "@/shared/lib";
import {
  Badge,
  CheckCircleIcon,
  ChevronLeftIcon,
  GlobeIcon,
  IconButton,
  ShareIcon,
  StarIcon,
} from "@/shared/ui";

import type { CompanyProfileCompany } from "../model/types";

interface ProfileHeaderProps {
  profile: CompanyProfileCompany;
  onShare: () => void;
  /** Prefer a fixed back target when history may leave the cabinet flow. */
  backTo?: string;
}

/**
 * Mockup header: back · title · share, then logo / name / verified / country /
 * rating chrome / verified badge. Platinum is omitted until we have a tier field.
 */
export function ProfileHeader({ profile, onShare, backTo }: ProfileHeaderProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const lang = coerceLang(i18n.language);
  const name = profile.short_name ?? profile.legal_name ?? "—";
  const country = countryName(profile.jurisdiction, lang);
  const initial = name.slice(0, 1).toUpperCase();

  return (
    <div className="space-y-4" data-testid="seller-profile-header">
      <header className="flex items-center gap-2">
        <IconButton
          label={t("common.back")}
          onClick={() => (backTo ? void navigate(backTo) : void navigate(-1))}
        >
          <ChevronLeftIcon size={20} />
        </IconButton>
        {/* The breadcrumb label, not the page heading. The company's NAME is the
            `h1` below — on the storefront this sheet is a company's landing
            page, and «Профиль компании» as its heading would be the same h1 on
            every one of them. */}
        <p className="min-w-0 flex-1 truncate text-base font-semibold text-text">
          {t("companyProfile.title")}
        </p>
        <IconButton label={t("market.detail.share")} onClick={onShare}>
          <ShareIcon size={18} />
        </IconButton>
      </header>

      <div className="flex items-start gap-3">
        {profile.logo_url ? (
          <img
            src={profile.logo_url}
            alt=""
            className="h-16 w-16 shrink-0 rounded-xl border border-border object-cover"
          />
        ) : (
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-info/20 text-xl font-bold text-info">
            {initial}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h1 className="text-xl font-semibold leading-tight text-text">{name}</h1>
            <CheckCircleIcon size={18} className="shrink-0 text-brand" />
          </div>
          <p className="mt-0.5 text-sm text-text-muted">{t("companyProfile.officialSupplier")}</p>
          {country ? (
            <p className="mt-1 flex items-center gap-1.5 text-sm text-text-muted">
              <GlobeIcon size={14} />
              {country}
            </p>
          ) : null}
          <p className="mt-1.5 flex items-center gap-1 text-sm text-text-subtle">
            <StarIcon size={14} className="text-gold" />
            {t("market.detail.ratingPending")}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Badge variant="verified">{t("companyProfile.verifiedCompany")}</Badge>
        {profile.roles.length > 0 ? <BusinessRoleBadges roles={profile.roles} /> : null}
      </div>

      {profile.verified_at ? (
        <p className="text-xs text-text-subtle">
          {t("companyProfile.onPlatformSince", {
            date: formatDate(profile.verified_at, lang),
          })}
        </p>
      ) : null}
    </div>
  );
}
