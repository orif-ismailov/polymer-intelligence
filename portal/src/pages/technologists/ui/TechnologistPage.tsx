import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { TechnologistAvatar, TechnologistRating, useTechnologist } from "@/entities/technologist";
import { InviteToRequest } from "@/features/tech-invite";
import { publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import {
  Badge,
  Card,
  CardBody,
  LinkButton,
  PageHeader,
  PageShell,
  Skeleton,
  SpecItem,
  SpecList,
} from "@/shared/ui";

/**
 * `/technologists/:profileId` — an expert's public professional profile.
 *
 * Server-rendered from the approved card; contacts are not in it at all — they
 * cross only when a factory accepts this expert's offer. The one session action,
 * «Пригласить к заявке», mounts after hydration (`InviteToRequest`).
 */
export function TechnologistPage() {
  const { t, i18n } = useTranslation();
  const { profileId } = useParams();
  const id = profileId && /^\d+$/.test(profileId) ? Number(profileId) : null;
  const query = useTechnologist(id);
  const card = query.data;
  const origin = publicSiteOrigin();
  const selfHref = `/technologists/${id ?? ""}`;
  const { canonical, alternates } = useCanonical(origin, selfHref, SUPPORTED_LANGS, i18n.language);

  if (query.isLoading) {
    return (
      <PageShell width="storefront">
        <Skeleton className="h-40 w-full" />
      </PageShell>
    );
  }
  if (!card) {
    return (
      <PageShell width="storefront" className="py-20 text-center">
        <p className="text-lg font-semibold text-text">{t("technologists.notFound")}</p>
        <div className="mt-6">
          <LinkButton to="/technologists" variant="outline">
            {t("technologists.backToCatalog")}
          </LinkButton>
        </div>
      </PageShell>
    );
  }

  const name = card.full_name ?? t("technologists.untitled");
  const place = [card.city, card.country].filter(Boolean).join(", ");

  return (
    <>
      <Seo
        title={t("technologists.profileMetaTitle", { name })}
        description={card.title ?? t("technologists.subtitle")}
        canonical={canonical}
        alternates={alternates}
      />
      <PageShell width="storefront">
        <PageHeader backTo="/technologists" backLabel={t("technologists.backToCatalog")} title={name} />

        <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-w-0 space-y-6">
            <Card>
              <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-start">
                <TechnologistAvatar photoUrl={card.photo_url} size="lg" />
                <div className="min-w-0 flex-1 space-y-2">
                  {card.title ? <p className="text-base font-medium text-text">{card.title}</p> : null}
                  {place ? <p className="text-sm text-text-muted">{place}</p> : null}
                  <div className="flex flex-wrap items-center gap-3">
                    <TechnologistRating avg={card.rating_avg} count={card.rating_count} />
                    <Badge variant="verified">{t("technologists.profileVerified")}</Badge>
                  </div>
                  {card.bio ? (
                    <p className="whitespace-pre-line pt-2 text-sm text-text-muted">{card.bio}</p>
                  ) : null}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardBody className="space-y-5">
                <ChipRow title={t("technologists.fields.processes")} values={card.processes.map((p) => t(`technologists.process.${p}`))} tone="brand" />
                <ChipRow title={t("technologists.fields.materials")} values={card.materials} />
                <ChipRow title={t("technologists.fields.industries")} values={card.industries.map((v) => t(`technologists.industry.${v}`))} />
                <ChipRow title={t("technologists.fields.equipment")} values={card.equipment_brands} />
              </CardBody>
            </Card>
          </div>

          <aside className="space-y-4">
            <Card>
              <CardBody>
                <SpecList>
                  {card.years_experience != null ? (
                    <SpecItem label={t("technologists.fields.years")} value={card.years_experience} numeric />
                  ) : null}
                  {card.projects_count != null ? (
                    <SpecItem label={t("technologists.fields.projects")} value={card.projects_count} numeric />
                  ) : null}
                  {card.countries_count != null ? (
                    <SpecItem label={t("technologists.fields.countries")} value={card.countries_count} numeric />
                  ) : null}
                  <SpecItem
                    label={t("technologists.fields.formats")}
                    value={card.work_formats.map((f) => t(`technologists.format.${f}`)).join(", ")}
                  />
                  <SpecItem
                    label={t("technologists.fields.languages")}
                    value={card.languages.map((l) => t(`technologists.language.${l}`)).join(", ")}
                  />
                </SpecList>
              </CardBody>
            </Card>
            <InviteToRequest profileId={card.id} selfHref={selfHref} />
          </aside>
        </div>
      </PageShell>
    </>
  );
}

function ChipRow({
  title,
  values,
  tone,
}: {
  title: string;
  values: string[];
  tone?: "brand";
}) {
  if (values.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold text-text">{title}</h2>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {values.map((v) => (
          <Badge key={v} tone={tone ?? "neutral"}>
            {v}
          </Badge>
        ))}
      </div>
    </section>
  );
}
