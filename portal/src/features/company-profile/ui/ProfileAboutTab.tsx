import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import type { PublicCompanyProfile } from "@/entities/market";
import { coerceLang } from "@/shared/i18n";
import { formatDate } from "@/shared/lib";
import {
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Handshake,
  Languages,
} from "lucide-react";
import {
  Card,
  CardBody,
  EmptyState,
  SpecItem,
  SpecList,
} from "@/shared/ui";

interface ProfileAboutTabProps {
  profile: PublicCompanyProfile;
}

function Stat({
  icon,
  label,
}: {
  icon: ReactNode;
  label: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-1 text-center">
      <span className="text-brand">{icon}</span>
      <span className="text-[11px] leading-tight text-text-muted">{label}</span>
    </div>
  );
}

function PendingKpi({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-dashed border-border bg-surface-2 px-3 py-4 text-center">
      <p className="text-lg font-semibold text-text-subtle">—</p>
      <p className="mt-1 text-xs text-text-muted">{label}</p>
    </div>
  );
}

/**
 * «О компании» — real fields (form, address, founded, roles, offer count) plus
 * honest pending chrome for KPIs / certificates / advantages the mockup paints
 * but the model does not store yet.
 */
export function ProfileAboutTab({ profile }: ProfileAboutTabProps) {
  const { t, i18n } = useTranslation();
  const lang = coerceLang(i18n.language);
  const name = profile.legal_name ?? profile.short_name ?? "—";
  const roleLabel =
    profile.roles.length > 0
      ? profile.roles.map((r) => t(`businessRole.${r}`, { defaultValue: r })).join(" · ")
      : "—";

  return (
    <div className="space-y-4" data-testid="seller-profile-about">
      <Card>
        <CardBody>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat
              icon={<Calendar size={18} strokeWidth={1.75} aria-hidden />}
              label={
                profile.verified_at
                  ? t("companyProfile.statSince", {
                      date: formatDate(profile.verified_at, lang),
                    })
                  : t("companyProfile.statSincePending")
              }
            />
            <Stat
              icon={<Handshake size={18} strokeWidth={1.75} aria-hidden />}
              label={t("companyProfile.statOffers", { count: profile.offer_count })}
            />
            <Stat
              icon={<Clock size={18} strokeWidth={1.75} aria-hidden />}
              label={t("companyProfile.statResponsePending")}
            />
            <Stat
              icon={<Languages size={18} strokeWidth={1.75} aria-hidden />}
              label={t("companyProfile.statLanguages")}
            />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <h3 className="text-sm font-semibold text-text">{t("companyProfile.about")}</h3>
          {profile.legal_form || profile.legal_address ? (
            <p className="text-sm leading-relaxed text-text">
              {[
                profile.legal_form ? t("companyProfile.aboutForm", { form: profile.legal_form }) : null,
                profile.legal_address
                  ? t("companyProfile.aboutAddress", { address: profile.legal_address })
                  : null,
              ]
                .filter(Boolean)
                .join(" ")}
            </p>
          ) : (
            <p className="text-sm text-text-muted">{t("companyProfile.aboutEmpty")}</p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <h3 className="text-sm font-semibold text-text">{t("companyProfile.kpiTitle")}</h3>
          <div className="grid grid-cols-2 gap-2">
            <PendingKpi label={t("companyProfile.kpiOnTime")} />
            <PendingKpi label={t("companyProfile.kpiRating")} />
            <PendingKpi label={t("companyProfile.kpiClients")} />
            <PendingKpi label={t("companyProfile.kpiCountries")} />
          </div>
          <p className="text-xs text-text-subtle">{t("companyProfile.kpiPendingHint")}</p>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <h3 className="text-sm font-semibold text-text">{t("companyProfile.certificates")}</h3>
          <EmptyState
            className="border-0 bg-transparent px-0 py-6"
            icon={<Building2 size={24} strokeWidth={1.75} aria-hidden />}
            title={t("companyProfile.certificatesEmpty")}
            description={t("companyProfile.certificatesEmptyBody")}
          />
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <h3 className="mb-3 text-sm font-semibold text-text">{t("companyProfile.details")}</h3>
          <SpecList>
            <SpecItem label={t("companyProfile.fullName")} value={name} />
            <SpecItem label={t("companyProfile.companyType")} value={roleLabel} />
            <SpecItem
              label={t("companyProfile.headOffice")}
              value={profile.legal_address?.trim() || "—"}
            />
            <SpecItem
              label={t("companyProfile.founded")}
              value={
                profile.registration_date
                  ? formatDate(profile.registration_date, lang)
                  : "—"
              }
            />
            <SpecItem label={t("companyProfile.jurisdiction")} value={profile.jurisdiction} />
          </SpecList>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="space-y-3">
          <h3 className="text-sm font-semibold text-text">{t("companyProfile.advantages")}</h3>
          <ul className="space-y-2">
            {(
              [
                t("companyProfile.advantageVerified"),
                profile.offer_count > 0
                  ? t("companyProfile.advantageOffers", { count: profile.offer_count })
                  : null,
              ] as (string | null)[]
            )
              .filter(Boolean)
              .map((text) => (
                <li key={text as string} className="flex items-start gap-2 text-sm text-text">
                  <CheckCircle2
                    size={16}
                    strokeWidth={1.75}
                    className="mt-0.5 shrink-0 text-brand"
                    aria-hidden
                  />
                  <span>{text}</span>
                </li>
              ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
