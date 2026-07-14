/**
 * IncotermsField — the Delivery Terms (Incoterms) picker with built-in guidance.
 *
 * A segmented selector plus two layers of help, so a seller unfamiliar with trade
 * terms can choose confidently without leaving the form:
 *   1. A live, plain-language one-liner under the control that updates as they tap a
 *      term (announced to screen readers via aria-live).
 *   2. A "What do these mean?" trigger opening IncotermsGuideModal — a full reference
 *      with the responsibility breakdown for every term.
 *
 * Self-contained and token-styled so both SellOffer (create) and EditOffer share it.
 */

import { useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import Segmented from "./Segmented";
import IncotermsGuideModal from "./IncotermsGuideModal";
import { INCOTERM_CODES, getIncoterm } from "../util/incoterms";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

const label: CSSProperties = {
  fontSize: "13px",
  fontWeight: 500,
  color: "var(--text-muted)",
};

export default function IncotermsField({ value, onChange }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selected = getIncoterm(value);

  function closeGuide() {
    setOpen(false);
    triggerRef.current?.focus(); // return focus to the trigger for keyboard users
  }

  return (
    <div style={{ marginBottom: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", marginBottom: "6px" }}>
        <span style={label}>{t("wizard.incoterms")}</span>
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen(true)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            minHeight: "32px",
            padding: "4px 8px",
            border: "none",
            background: "transparent",
            color: "var(--blue)",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <Info size={14} aria-hidden="true" />
          {t("incotermsGuide.trigger")}
        </button>
      </div>

      <Segmented<string>
        value={value}
        options={INCOTERM_CODES.map((c) => ({ value: c, label: c }))}
        onChange={onChange}
        ariaLabel={t("wizard.incoterms")}
      />

      {selected && (
        <p
          aria-live="polite"
          style={{ margin: "8px 0 0", fontSize: "12px", lineHeight: 1.5, color: "var(--text-muted)" }}
        >
          <span style={{ fontWeight: 700, color: "var(--text)" }}>{selected.code}</span>
          {" — "}
          {t(`incotermsGuide.terms.${selected.code}.summary`)}
        </p>
      )}

      <IncotermsGuideModal open={open} onClose={closeGuide} highlight={value} />
    </div>
  );
}
