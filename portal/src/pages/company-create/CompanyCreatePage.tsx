import { type ReactNode } from "react";

import { useParams } from "react-router-dom";

import { CompanyWizard, RegistrationDone } from "@/features/company-wizard";

/**
 * Registration flow shell. Full-screen and outside `AppShell`: the mockups give
 * these sheets their own chrome, and the cabinet nav has no active company to be
 * scoped to during a first registration anyway.
 */
function FlowScreen({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="mx-auto w-full max-w-md px-4 pb-12 pt-4">{children}</div>
    </div>
  );
}

/** Company registration wizard page. Orchestration only — the wizard owns state. */
export function CompanyCreatePage() {
  return (
    <FlowScreen>
      <CompanyWizard />
    </FlowScreen>
  );
}

/** «Регистрация завершена!» — the closing sheet, addressable by company id. */
export function CompanyCreatedPage() {
  const params = useParams<{ companyId: string }>();
  const companyId = Number(params.companyId);

  return (
    <FlowScreen>
      {Number.isInteger(companyId) ? <RegistrationDone companyId={companyId} /> : null}
    </FlowScreen>
  );
}
