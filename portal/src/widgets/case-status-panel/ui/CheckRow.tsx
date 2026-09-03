import { useTranslation } from "react-i18next";

import { CheckStatusBadge } from "@/entities/verification";
import type { CaseCheck } from "@/entities/verification";
import { useEnumLabels } from "@/shared/i18n";

type Translate = ReturnType<typeof useTranslation>["t"];
type EnumLabel = ReturnType<typeof useEnumLabels>;

/**
 * Turn one check's `detail` payload into sentences the applicant can act on.
 *
 * The vocabulary is the backend's, verbatim: `app/domains/verification/checks.py`
 * is the only writer of these payloads, and the portal receives them whole
 * (`CheckOut.detail` = `check.result`).
 *
 * This exists because the previous version probed for `message`/`reason`/
 * `detail`/`note`/`explanation` — and `bank_requisites`, the check that most
 * often blocks a case, writes none of them. It writes `problems: [{last4,
 * issue}]`. So the one screen telling a client why their company was sent back
 * said «Дополнительная информация отсутствует.» about the very field they had to
 * fix. Nothing errored; the information just never arrived.
 *
 * The staff twin of this table lives in the dashboard's verification case page,
 * where the raw payload is also shown. Here it is not: this is the client's
 * screen, and a JSON dump is not an instruction.
 *
 * There is deliberately NO free-text fallback. Every `reason`/`note` these checks
 * write is a machine code (`awaiting_human_review`, `no_snapshot`,
 * `signature_invalid`), so the old probe printed those codes at the client —
 * which the browser caught the moment this table went in. An unmapped check
 * shows «Дополнительная информация отсутствует.» instead: less, but true.
 */
function explain(check: CaseCheck, t: Translate, label: EnumLabel): string[] {
  // `unavailable` is about the SOURCE, not the company, whatever the check type.
  if (check.status === "unavailable") return [t("verification.findings.unavailable")];
  if (check.check_type === "manual_kyb" && check.status === "pending") {
    return [t("verification.findings.manualPending")];
  }

  const detail = check.detail ?? {};
  const findings: string[] = [];

  switch (check.check_type) {
    case "tax_id_format": {
      if (check.status !== "failed") break;
      const digits = typeof detail["digits"] === "number" ? detail["digits"] : 0;
      findings.push(
        digits === 0
          ? t("verification.findings.taxIdEmpty")
          : t("verification.findings.taxIdDigits", { digits }),
      );
      break;
    }

    case "bank_requisites": {
      if (detail["reason"] === "no_bank_account") {
        findings.push(t("verification.findings.noBankAccount"));
        break;
      }
      for (const problem of bankProblems(detail["problems"])) {
        findings.push(
          t("verification.findings.bankAccount", {
            last4: problem.last4,
            problem: label("verification.findings.bankIssue", problem.issue),
          }),
        );
      }
      break;
    }

    case "documents_complete": {
      const missing = stringList(detail["missing"]);
      if (missing.length > 0) {
        findings.push(
          t("verification.findings.missingDocuments", {
            list: missing.map((kind) => label("documentKind", kind)).join(", "),
          }),
        );
      }
      break;
    }

    case "gov_registry": {
      const reason = detail["reason"];
      const registryStatus = detail["registry_status"];
      if (reason === "inn_mismatch") findings.push(t("verification.findings.registryInnMismatch"));
      if (registryStatus === "liquidated") {
        findings.push(t("verification.findings.registryLiquidated"));
      }
      if (registryStatus === "suspended") {
        findings.push(t("verification.findings.registrySuspended"));
      }
      if (reason === "status_unknown") {
        findings.push(t("verification.findings.registryStatusUnknown"));
      }
      if (detail["name_matches"] === false) {
        findings.push(
          t("verification.findings.registryNameMismatch", {
            name: text(detail["registry_name"]),
          }),
        );
      }
      break;
    }

    case "vat_status": {
      // Not being a VAT payer is legally normal in Uzbekistan — say so, or the
      // warning chip reads as something the client has to go and fix.
      if (detail["registered"] === false) findings.push(t("verification.findings.vatNotRegistered"));
      break;
    }

    case "eimzo_signature": {
      // The sidecar's `reason` is its own vocabulary, not ours, and it is not
      // something a client can act on. Staff see it in the raw payload.
      if (check.status === "failed") findings.push(t("verification.findings.eimzoFailed"));
      break;
    }
  }

  return findings;
}

interface BankProblem {
  last4: string;
  issue: string;
}

function bankProblems(value: unknown): BankProblem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry) => {
    if (typeof entry !== "object" || entry === null) return [];
    const { last4, issue } = entry as Record<string, unknown>;
    if (typeof issue !== "string") return [];
    return [{ last4: typeof last4 === "string" ? last4 : "—", issue }];
  });
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string");
}

/** A JSONB field as display text — never `[object Object]`. */
function text(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.trim() !== "" ? value : fallback;
}

interface CheckRowProps {
  check: CaseCheck;
}

export function CheckRow({ check }: CheckRowProps) {
  const { t } = useTranslation();
  const label = useEnumLabels();
  const findings = explain(check, t, label);

  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text">{label("verification.checkTypes", check.check_type)}</p>
        {findings.length === 0 ? (
          <p className="mt-0.5 text-xs text-text-muted">{t("verification.checkDetail.empty")}</p>
        ) : (
          <ul className="mt-0.5 space-y-0.5">
            {findings.map((finding) => (
              <li key={finding} className="text-xs text-text-muted">
                {finding}
              </li>
            ))}
          </ul>
        )}
      </div>
      <CheckStatusBadge status={check.status} />
    </li>
  );
}
