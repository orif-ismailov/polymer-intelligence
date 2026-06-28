/**
 * RadioCard — a tappable selection card with a green check when chosen
 * (IMG_0044 delivery-terms / urgency style). Token-themed.
 */

import type { CSSProperties } from "react";
import { CheckCircle2 } from "lucide-react";

interface RadioCardProps {
  selected: boolean;
  label: string;
  description?: string;
  onClick: () => void;
}

export default function RadioCard({ selected, label, description, onClick }: RadioCardProps) {
  const style: CSSProperties = {
    display: "flex",
    width: "100%",
    textAlign: "left",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
    padding: "14px",
    borderRadius: "var(--r-md)",
    border: selected ? "1px solid var(--green)" : "1px solid var(--border)",
    background: "var(--surface)",
    cursor: "pointer",
    marginBottom: "8px",
    color: "var(--text)",
  };
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} style={style}>
      <span>
        <span style={{ display: "block", fontSize: "15px", fontWeight: 600 }}>{label}</span>
        {description && (
          <span style={{ display: "block", fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
            {description}
          </span>
        )}
      </span>
      {selected && <CheckCircle2 size={20} color="var(--green)" style={{ flex: "0 0 auto" }} />}
    </button>
  );
}
