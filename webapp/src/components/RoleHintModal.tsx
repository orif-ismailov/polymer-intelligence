/**
 * First-run role hint (IMG_0046 / spec): asks Buyer vs Seller once, then routes to
 * that default tab. Soft hint, not a gate — everything stays reachable. Renders
 * nothing once a role has been chosen (persisted in roleStore).
 */

import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShoppingCart, Store } from "lucide-react";

import { useRoleStore, type Role } from "../store/roleStore";

export default function RoleHintModal() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const role = useRoleStore((s) => s.role);
  const setRole = useRoleStore((s) => s.setRole);

  if (role !== null) return null;

  function choose(r: Role) {
    setRole(r);
    navigate(r === "buyer" ? "/market" : "/sell");
  }

  const overlay: CSSProperties = {
    position: "fixed",
    inset: 0,
    background: "var(--overlay)",
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "center",
    zIndex: 100,
  };
  const sheet: CSSProperties = {
    width: "100%",
    maxWidth: "480px",
    background: "var(--surface)",
    borderTopLeftRadius: "var(--r-lg)",
    borderTopRightRadius: "var(--r-lg)",
    padding: "24px 16px calc(24px + env(safe-area-inset-bottom))",
    boxShadow: "var(--shadow)",
  };
  const card: CSSProperties = {
    display: "flex",
    gap: "14px",
    alignItems: "center",
    width: "100%",
    textAlign: "start",
    padding: "16px",
    borderRadius: "var(--r-md)",
    border: "1px solid var(--border)",
    background: "var(--surface-2)",
    cursor: "pointer",
    marginTop: "12px",
    color: "var(--text)",
  };
  const iconWrap = (bg: string, fg: string): CSSProperties => ({
    flex: "0 0 auto",
    width: "44px",
    height: "44px",
    borderRadius: "var(--r-full)",
    background: bg,
    color: fg,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  });

  return (
    <div style={overlay} role="dialog" aria-modal="true" aria-label={t("roleHint.title")}>
      <div style={sheet}>
        <h2 style={{ margin: "0 0 6px", fontSize: "20px", fontWeight: 700, color: "var(--text)" }}>
          {t("roleHint.title")}
        </h2>
        <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted)" }}>
          {t("roleHint.subtitle")}
        </p>

        <button type="button" style={card} onClick={() => choose("buyer")}>
          <span style={iconWrap("var(--chip-ok-bg)", "var(--green)")}>
            <ShoppingCart size={22} color="var(--green)" />
          </span>
          <span>
            <span style={{ display: "block", fontSize: "15px", fontWeight: 600 }}>
              {t("roleHint.buyer")}
            </span>
            <span style={{ display: "block", fontSize: "13px", color: "var(--text-muted)", marginTop: "2px" }}>
              {t("roleHint.buyerDesc")}
            </span>
          </span>
        </button>

        <button type="button" style={card} onClick={() => choose("seller")}>
          <span style={iconWrap("var(--chip-warn-bg)", "var(--orange)")}>
            <Store size={22} color="var(--orange)" />
          </span>
          <span>
            <span style={{ display: "block", fontSize: "15px", fontWeight: 600 }}>
              {t("roleHint.seller")}
            </span>
            <span style={{ display: "block", fontSize: "13px", color: "var(--text-muted)", marginTop: "2px" }}>
              {t("roleHint.sellerDesc")}
            </span>
          </span>
        </button>
      </div>
    </div>
  );
}
