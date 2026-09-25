import type { ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { LEGAL_VALUES, publicSiteOrigin } from "@/shared/config";
import { SUPPORTED_LANGS } from "@/shared/i18n";
import { Seo, useCanonical } from "@/shared/seo";
import { PageHeader, PageShell } from "@/shared/ui";

/**
 * A section of a legal page, described by its i18n keys under `prefix`.
 *
 * The TEXT lives in the six locale files; this only says which keys a section
 * has, so every language renders the same structure. `paragraphs` and `items`
 * are key suffixes (`body`, `intro`; `items.account`, …) — a key missing from a
 * locale is a runtime error in this app, which is why the locale trees are kept
 * identical rather than letting a language drop a clause.
 */
export interface LegalSection {
  id: string;
  /** Paragraphs rendered BEFORE the list. */
  lead?: readonly string[];
  /** List item keys, relative to `${prefix}.${id}.items`. */
  items?: readonly string[];
  /** Render the list numbered (steps) rather than bulleted. */
  ordered?: boolean;
  /** Paragraphs rendered AFTER the list. */
  trail?: readonly string[];
  /** Extra content after the section's text (e.g. a CTA). */
  extra?: ReactNode;
}

interface LegalDocumentProps {
  /** i18n prefix, e.g. `legal.privacy`. */
  prefix: string;
  /** Public path, for the canonical URL. */
  path: string;
  sections: readonly LegalSection[];
  /** Rendered between the header and the first section. */
  notice?: ReactNode;
  /** Rendered after the last section. */
  footer?: ReactNode;
}

/**
 * Shared chrome for `/privacy` and `/account-deletion`: SEO, title, revision date,
 * then each section as an `<h2>` with its paragraphs and list.
 *
 * Server-rendered like the rest of the storefront — both app stores fetch these
 * URLs, and a reviewer's crawler must see the text without running the bundle.
 * The operator's name, contact and hosting come from `shared/config/legal.ts`
 * as interpolation values, so the six locales cannot disagree about them.
 */
export function LegalDocument({ prefix, path, sections, notice, footer }: LegalDocumentProps) {
  const { t, i18n } = useTranslation();
  const origin = publicSiteOrigin();
  const { canonical, alternates } = useCanonical(origin, path, SUPPORTED_LANGS, i18n.language);
  const tt = (key: string): string => t(key, LEGAL_VALUES);

  return (
    <>
      <Seo
        title={tt(`${prefix}.metaTitle`)}
        description={tt(`${prefix}.metaDescription`)}
        canonical={canonical}
        alternates={alternates}
      />

      <PageShell width="storefront" className="max-w-3xl">
        <PageHeader title={tt(`${prefix}.title`)} subtitle={tt("legal.updated")} />

        {notice ? <div className="mt-6">{notice}</div> : null}

        <p className="mt-6 text-sm leading-relaxed text-text-muted">{tt(`${prefix}.intro`)}</p>

        {sections.map((section) => {
          const base = `${prefix}.${section.id}`;
          const List = section.ordered ? "ol" : "ul";
          return (
            <section key={section.id} aria-labelledby={`legal-${section.id}`} className="mt-8">
              <h2 id={`legal-${section.id}`} className="text-base font-semibold text-text">
                {tt(`${base}.title`)}
              </h2>
              {section.lead?.map((p) => (
                <p key={p} className="mt-3 text-sm leading-relaxed text-text-muted">
                  {tt(`${base}.${p}`)}
                </p>
              ))}
              {section.items && section.items.length > 0 ? (
                <List
                  className={
                    section.ordered
                      ? "mt-3 list-decimal space-y-2 ps-5 text-sm leading-relaxed text-text-muted"
                      : "mt-3 list-disc space-y-2 ps-5 text-sm leading-relaxed text-text-muted"
                  }
                >
                  {section.items.map((item) => (
                    <li key={item}>{tt(`${base}.${section.ordered ? "steps" : "items"}.${item}`)}</li>
                  ))}
                </List>
              ) : null}
              {section.trail?.map((p) => (
                <p key={p} className="mt-3 text-sm leading-relaxed text-text-muted">
                  {tt(`${base}.${p}`)}
                </p>
              ))}
              {section.extra}
            </section>
          );
        })}

        {footer ? <div className="mt-10 border-t border-border pt-6">{footer}</div> : null}
      </PageShell>
    </>
  );
}
