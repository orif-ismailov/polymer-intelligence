import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

import { Alert, LinkButton } from "@/shared/ui";

import { type LegalSection, LegalDocument } from "./LegalDocument";

/**
 * `/account-deletion` — the public page Google Play requires beside the in-app
 * path: how to delete an account (app and web), what goes, what the law keeps,
 * and who to write to without access.
 *
 * Also where the cabinet lands after a deletion, with `state.deleted` set. That
 * state exists only after a client-side navigation, so the server render — the
 * version a store reviewer fetches — never carries the confirmation.
 */
export function AccountDeletionPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const deleted = (location.state as { deleted?: boolean } | null)?.deleted === true;

  const sections: readonly LegalSection[] = [
    { id: "inApp", items: ["s1", "s2", "s3", "s4"], ordered: true },
    {
      id: "web",
      items: ["s1", "s2", "s3"],
      ordered: true,
      extra: deleted ? null : (
        <div className="mt-4">
          <LinkButton to="/cabinet/settings" variant="secondary" size="sm">
            {t("legal.deletion.web.cta")}
          </LinkButton>
        </div>
      ),
    },
    {
      id: "deleted",
      items: ["profile", "login", "sessions", "memberships", "technologist", "personal"],
    },
    {
      id: "retained",
      lead: ["intro"],
      items: ["companies", "contracts", "deals", "messages", "audit"],
      trail: ["outro"],
    },
    { id: "noAccess", lead: ["body"] },
  ];

  return (
    <LegalDocument
      prefix="legal.deletion"
      path="/account-deletion"
      sections={sections}
      notice={deleted ? <Alert tone="success" title={t("legal.deletion.done")} /> : null}
      footer={
        <Link to="/privacy" className="text-sm font-medium text-brand hover:underline">
          {t("legal.deletion.privacyLink")}
        </Link>
      }
    />
  );
}
