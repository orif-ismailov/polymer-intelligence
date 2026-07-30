import { useTranslation } from "react-i18next";

import {
  FlaskIcon,
  GlobeIcon,
  IconTile,
  ScaleIcon,
  ShieldIcon,
  TraderIcon,
} from "@/shared/ui";

import { ASSURANCE_BLOCKS, TRUST_CHIPS } from "../model/constants";

const CHIP_GLYPH = {
  safe: <ShieldIcon size={13} />,
  legal: <ScaleIcon size={13} />,
  professional: <TraderIcon size={13} />,
  international: <GlobeIcon size={13} />,
} as const;

/**
 * The four chips in the mockup's masthead — «Безопасно · Легально ·
 * Профессионально · Международный стандарт».
 *
 * They say what the platform is for, not what this offer is, which is why they
 * live in the flow's chrome and carry no state. Hidden below `sm`: on a phone
 * the rail and the sheet are the screen, and four reassurance pills pushed the
 * first field below the fold.
 */
export function TrustChips() {
  const { t } = useTranslation();
  return (
    <ul className="hidden flex-wrap gap-2 sm:flex">
      {TRUST_CHIPS.map((chip) => (
        <li
          key={chip}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-muted"
        >
          <span className="text-brand">{CHIP_GLYPH[chip]}</span>
          {t(`offerWizard.trust.${chip}`)}
        </li>
      ))}
    </ul>
  );
}

const ASSURANCE_GLYPH = {
  deals: <ShieldIcon size={18} />,
  trade: <ScaleIcon size={18} />,
  lab: <FlaskIcon size={18} />,
  b2b: <TraderIcon size={18} />,
  global: <GlobeIcon size={18} />,
} as const;

/**
 * The mockup's footer strip: five blocks explaining what the platform does
 * around the listing you are writing (escrow, legality checks, laboratory
 * support, B2B tooling, export).
 */
export function AssuranceStrip() {
  const { t } = useTranslation();
  return (
    <ul className="grid gap-4 border-t border-border pt-6 sm:grid-cols-2 lg:grid-cols-3">
      {ASSURANCE_BLOCKS.map((block) => (
        <li key={block} className="flex items-start gap-3">
          <IconTile tone="muted" size="sm">
            {ASSURANCE_GLYPH[block]}
          </IconTile>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-text">
              {t(`offerWizard.assurance.${block}.title`)}
            </span>
            <span className="mt-0.5 block text-xs leading-relaxed text-text-muted">
              {t(`offerWizard.assurance.${block}.body`)}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
