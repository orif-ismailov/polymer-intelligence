"use client";

/**
 * Account-type profile sections — manufacturer/logistics/laboratory.
 *
 * Renders the three `companies.{manufacturer,logistics,laboratory}_profile`
 * JSONB blobs (backend/app/schemas/portal_company.py: ManufacturerProfileIn /
 * LogisticsProfileIn / LaboratoryProfileIn). The column is untyped JSONB on
 * the server too, so values are read defensively rather than trusted — an
 * older row or an in-flight schema change should degrade to "field omitted",
 * not a crash. Shared across companies/[id] and verification/[id], hence its
 * own file (mirrors company-status.tsx/company-licenses.tsx) and its own
 * `useTranslations("companies")` call independent of the host page's
 * namespace, the same idiom CompanyRoleBadge already uses.
 */

import { useTranslations } from "next-intl";

interface Props {
  manufacturerProfile: Record<string, unknown> | null;
  logisticsProfile: Record<string, unknown> | null;
  laboratoryProfile: Record<string, unknown> | null;
}

// `t.raw()` returns the message subtree verbatim; these mirror the exact key
// sets under companies.profileSections.* in messages/*.json. Typed as plain
// interfaces (not Record<string, string>) so property access stays a plain
// `string` under `noUncheckedIndexedAccess` — an index-signature type would
// widen every access to `string | undefined`.
interface ManufacturerLabels {
  title: string;
  productionType: string;
  mainProducts: string;
  annualCapacityTons: string;
  productionLines: string;
  employees: string;
  foundedYear: string;
  isoCertification: string;
  moqTons: string;
  minAnnualVolumeTons: string;
  additionalOther: string;
  markets: string;
  exportCountries: string;
  additionalRequirements: string;
  financialRequirements: string;
}

interface LogisticsLabels {
  title: string;
  city: string;
  tariffModel: string;
  yearsExperience: string;
  projectsCompleted: string;
  description: string;
  services: string;
  fromCountries: string;
  toCountries: string;
  popularRoutes: string;
  cargoTypes: string;
  capabilities: string;
}

interface LaboratoryLabels {
  title: string;
  city: string;
  website: string;
  email: string;
  phone: string;
  yearsExperience: string;
  studiesCompleted: string;
  avgTurnaroundDays: string;
  description: string;
  accreditations: string;
  methods: string;
}

export function CompanyProfileSections({
  manufacturerProfile,
  logisticsProfile,
  laboratoryProfile,
}: Props) {
  if (!manufacturerProfile && !logisticsProfile && !laboratoryProfile) return null;
  return (
    <>
      {manufacturerProfile && <ManufacturerSection profile={manufacturerProfile} />}
      {logisticsProfile && <LogisticsSection profile={logisticsProfile} />}
      {laboratoryProfile && <LaboratorySection profile={laboratoryProfile} />}
    </>
  );
}

// ─── Manufacturer ──────────────────────────────────────────────────────────────

function ManufacturerSection({ profile }: { profile: Record<string, unknown> }) {
  const t = useTranslations("companies");
  const s = t.raw("profileSections.manufacturer") as ManufacturerLabels;

  const financialRequirements = asBoolDict(profile.financial_requirements);
  const trueRequirements = Object.keys(financialRequirements).filter(
    (k) => financialRequirements[k],
  );

  return (
    <section className="rounded-lg border border-border bg-background-secondary p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
        {s.title}
      </h2>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={s.productionType} value={asString(profile.production_type)} />
        <Field label={s.mainProducts} value={asString(profile.main_products)} />
        <Field label={s.annualCapacityTons} value={asNumber(profile.annual_capacity_tons)} />
        <Field label={s.productionLines} value={asNumber(profile.production_lines)} />
        <Field label={s.employees} value={asNumber(profile.employees)} />
        <Field label={s.foundedYear} value={asNumber(profile.founded_year)} />
        <Field label={s.isoCertification} value={asString(profile.iso_certification)} />
        <Field label={s.moqTons} value={asNumber(profile.moq_tons)} />
        <Field label={s.minAnnualVolumeTons} value={asNumber(profile.min_annual_volume_tons)} />
        <Field label={s.additionalOther} value={asString(profile.additional_other)} />
      </dl>
      <Chips label={s.markets} values={asStringArray(profile.markets)} />
      <Chips label={s.exportCountries} values={asStringArray(profile.export_countries)} />
      <Chips
        label={s.additionalRequirements}
        values={asStringArray(profile.additional_requirements)}
      />
      <Chips label={s.financialRequirements} values={trueRequirements} />
    </section>
  );
}

// ─── Logistics ─────────────────────────────────────────────────────────────────

function LogisticsSection({ profile }: { profile: Record<string, unknown> }) {
  const t = useTranslations("companies");
  const s = t.raw("profileSections.logistics") as LogisticsLabels;

  return (
    <section className="rounded-lg border border-border bg-background-secondary p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
        {s.title}
      </h2>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={s.city} value={asString(profile.city)} />
        <Field label={s.tariffModel} value={asString(profile.tariff_model)} />
        <Field label={s.yearsExperience} value={asNumber(profile.years_experience)} />
        <Field label={s.projectsCompleted} value={asNumber(profile.projects_completed)} />
        <Field label={s.description} value={asString(profile.description)} span />
      </dl>
      <Chips label={s.services} values={asStringArray(profile.services)} />
      <Chips label={s.fromCountries} values={asStringArray(profile.from_countries)} />
      <Chips label={s.toCountries} values={asStringArray(profile.to_countries)} />
      <Chips label={s.popularRoutes} values={asStringArray(profile.popular_routes)} />
      <Chips label={s.cargoTypes} values={asStringArray(profile.cargo_types)} />
      <Chips label={s.capabilities} values={asStringArray(profile.capabilities)} />
    </section>
  );
}

// ─── Laboratory ────────────────────────────────────────────────────────────────

function LaboratorySection({ profile }: { profile: Record<string, unknown> }) {
  const t = useTranslations("companies");
  const s = t.raw("profileSections.laboratory") as LaboratoryLabels;

  return (
    <section className="rounded-lg border border-border bg-background-secondary p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-foreground-muted">
        {s.title}
      </h2>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={s.city} value={asString(profile.city)} />
        <Field label={s.website} value={asString(profile.website)} />
        <Field label={s.email} value={asString(profile.email)} />
        <Field label={s.phone} value={asString(profile.phone)} />
        <Field label={s.yearsExperience} value={asNumber(profile.years_experience)} />
        <Field label={s.studiesCompleted} value={asNumber(profile.studies_completed)} />
        <Field label={s.avgTurnaroundDays} value={asNumber(profile.avg_turnaround_days)} />
        <Field label={s.description} value={asString(profile.description)} span />
      </dl>
      <Chips label={s.accreditations} values={asStringArray(profile.accreditations)} />
      <Chips label={s.methods} values={asStringArray(profile.methods)} />
    </section>
  );
}

// ─── Shared presentational helpers ─────────────────────────────────────────────

function Field({
  label,
  value,
  span,
}: {
  label: string;
  value: string | null;
  span?: boolean;
}) {
  return (
    <div className={span ? "sm:col-span-2 lg:col-span-3" : undefined}>
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className="mt-1 text-sm text-foreground break-words">{value || "—"}</dd>
    </div>
  );
}

function Chips({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs text-foreground-muted">{label}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="rounded bg-background-tertiary px-1.5 py-0.5 text-xs text-foreground"
          >
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Defensive JSONB readers ────────────────────────────────────────────────────

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function asNumber(value: unknown): string | null {
  return typeof value === "number" ? String(value) : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === "string");
}

function asBoolDict(value: unknown): Record<string, boolean> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
  return value as Record<string, boolean>;
}
