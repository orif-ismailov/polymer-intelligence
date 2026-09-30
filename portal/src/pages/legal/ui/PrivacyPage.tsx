import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { type LegalSection, LegalDocument } from "./LegalDocument";

const SECTIONS: readonly LegalSection[] = [
  { id: "operator", lead: ["body"] },
  {
    id: "collect",
    lead: ["intro"],
    items: [
      "account",
      "company",
      "documents",
      "trade",
      "messages",
      "photos",
      "eimzo",
      "didox",
      "technical",
    ],
  },
  {
    id: "purposes",
    items: ["service", "verification", "contracts", "communication", "security", "legal"],
  },
  { id: "basis", lead: ["body"] },
  {
    id: "processors",
    lead: ["intro"],
    items: ["hosting", "didox", "eimzo", "telegram", "llm"],
    trail: ["outro"],
  },
  { id: "retention", items: ["account", "company", "messages", "logs"] },
  {
    id: "rights",
    lead: ["intro"],
    items: ["access", "rectify", "delete", "withdraw", "complain"],
    trail: ["outro"],
  },
  { id: "mobile", lead: ["body"] },
  { id: "security", lead: ["body"] },
  { id: "minors", lead: ["body"] },
  { id: "changes", lead: ["body"] },
  { id: "contact", lead: ["body"] },
];

/**
 * `/privacy` — the privacy policy the app stores link to, for ai-imex.com and the
 * mobile apps alike. Public and server-rendered; the text is in `legal.privacy.*`.
 */
export function PrivacyPage() {
  const { t } = useTranslation();
  return (
    <LegalDocument
      prefix="legal.privacy"
      path="/privacy"
      sections={SECTIONS}
      footer={
        <Link to="/account-deletion" className="text-sm font-medium text-brand hover:underline">
          {t("public.footer.accountDeletion")}
        </Link>
      }
    />
  );
}
