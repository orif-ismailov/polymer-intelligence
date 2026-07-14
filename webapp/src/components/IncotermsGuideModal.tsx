/**
 * IncotermsGuideModal — a bottom-sheet reference explaining every delivery term.
 *
 * Follows the RoleHintModal sheet pattern (overlay + --surface sheet, safe-area
 * padding, role="dialog"/aria-modal). Each term is a card: plain-language summary,
 * a four-row responsibility grid (export customs · transport · insurance · import
 * customs) with Seller/Buyer badges, and where risk passes to the buyer. Written for
 * users with no international-trade background; the responsibility facts come from the
 * Incoterms® 2020 data module, the prose from i18n.
 *
 * Accessibility: labelled dialog, Escape to close, backdrop click to close, focus moves
 * into the sheet on open, page scroll locked while open, the sheet scrolls internally.
 */

import { useEffect, useRef, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { INCOTERMS, RESPONSIBILITY_ROWS, type IncotermInfo, type Party } from "../util/incoterms";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Code of the term the seller currently has selected — pinned first and marked. */
  highlight?: string;
}

const TITLE_ID = "incoterms-guide-title";

export default function IncotermsGuideModal({ open, onClose, highlight }: Props) {
  const { t } = useTranslation();
  const sheetRef = useRef<HTMLDivElement>(null);

  // Escape to close + lock the page scroll behind the sheet while it is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sheetRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  // Selected term first so the seller sees their choice explained without scrolling.
  const ordered = highlight
    ? [...INCOTERMS].sort((a, b) => (a.code === highlight ? -1 : b.code === highlight ? 1 : 0))
    : INCOTERMS;

  const overlay: CSSProperties = {
    position: "fixed",
    inset: 0,
    background: "var(--overlay)",
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "center",
    zIndex: 200,
  };
  const sheet: CSSProperties = {
    width: "100%",
    maxWidth: "480px",
    maxHeight: "88vh",
    display: "flex",
    flexDirection: "column",
    background: "var(--surface)",
    borderTopLeftRadius: "var(--r-lg)",
    borderTopRightRadius: "var(--r-lg)",
    boxShadow: "var(--shadow)",
    outline: "none",
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        tabIndex={-1}
        style={sheet}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header (sticky-feel: outside the scroll area) */}
        <div style={{ padding: "20px 16px 12px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" }}>
            <h2 id={TITLE_ID} style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text)" }}>
              {t("incotermsGuide.title")}
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label={t("incotermsGuide.close")}
              style={{
                flex: "0 0 auto",
                width: "32px",
                height: "32px",
                borderRadius: "var(--r-full)",
                border: "none",
                background: "var(--surface-2)",
                color: "var(--text-muted)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
              }}
            >
              <X size={18} />
            </button>
          </div>
          <p style={{ margin: "6px 0 0", fontSize: "13px", lineHeight: 1.5, color: "var(--text-muted)" }}>
            {t("incotermsGuide.subtitle")}
          </p>
        </div>

        {/* Scrollable term list */}
        <div
          style={{
            overflowY: "auto",
            WebkitOverflowScrolling: "touch",
            padding: "12px 16px calc(20px + env(safe-area-inset-bottom))",
            display: "flex",
            flexDirection: "column",
            gap: "10px",
          }}
        >
          {ordered.map((term) => (
            <TermCard key={term.code} term={term} selected={term.code === highlight} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TermCard({ term, selected }: { term: IncotermInfo; selected: boolean }) {
  const { t } = useTranslation();
  return (
    <section
      aria-current={selected ? "true" : undefined}
      style={{
        borderRadius: "var(--r-md)",
        border: `1px solid ${selected ? "var(--orange)" : "var(--border)"}`,
        background: "var(--surface-2)",
        padding: "14px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        <span
          style={{
            fontSize: "15px",
            fontWeight: 700,
            color: "var(--text)",
            letterSpacing: "0.02em",
          }}
        >
          {term.code}
        </span>
        <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>{term.fullName}</span>
        {selected && (
          <span
            style={{
              marginInlineStart: "auto",
              fontSize: "11px",
              fontWeight: 700,
              color: "var(--chip-warn-fg)",
              background: "var(--chip-warn-bg)",
              padding: "2px 8px",
              borderRadius: "var(--r-full)",
            }}
          >
            {t("incotermsGuide.selected")}
          </span>
        )}
      </div>

      <p style={{ margin: "8px 0 12px", fontSize: "13px", lineHeight: 1.55, color: "var(--text)" }}>
        {t(`incotermsGuide.terms.${term.code}.summary`)}
      </p>

      {/* Responsibility grid: who does what */}
      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "1fr auto", gap: "6px 12px", alignItems: "center" }}>
        {RESPONSIBILITY_ROWS.map((row) => (
          <div key={row.key} style={{ display: "contents" }}>
            <dt style={{ fontSize: "12px", color: "var(--text-muted)" }}>{t(row.labelKey)}</dt>
            <dd style={{ margin: 0, justifySelf: "end" }}>
              <PartyBadge party={term[row.key] as Party} />
            </dd>
          </div>
        ))}
        <dt style={{ fontSize: "12px", color: "var(--text-muted)" }}>{t("incotermsGuide.riskLabel")}</dt>
        <dd style={{ margin: 0, justifySelf: "end", fontSize: "12px", fontWeight: 600, color: "var(--text)", textAlign: "end" }}>
          {t(`incotermsGuide.risk.${term.riskAt}`)}
        </dd>
      </dl>
    </section>
  );
}

function PartyBadge({ party }: { party: Party }) {
  const { t } = useTranslation();
  const you = party === "you";
  return (
    <span
      style={{
        fontSize: "11px",
        fontWeight: 700,
        padding: "2px 8px",
        borderRadius: "var(--r-full)",
        whiteSpace: "nowrap",
        color: you ? "var(--chip-warn-fg)" : "var(--chip-ok-fg)",
        background: you ? "var(--chip-warn-bg)" : "var(--chip-ok-bg)",
      }}
    >
      {you ? t("incotermsGuide.party.you") : t("incotermsGuide.party.buyer")}
    </span>
  );
}
