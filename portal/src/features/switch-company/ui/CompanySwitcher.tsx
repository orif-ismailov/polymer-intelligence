import { useEffect, useRef, useState } from "react";

import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { CompanyStatusBadge, useActiveCompany } from "@/entities/company";
import type { CompanySummary } from "@/entities/company";
import { cn } from "@/shared/lib";
import { Button } from "@/shared/ui";

function companyLabel(company: CompanySummary, fallback: string): string {
  return company.short_name ?? company.legal_name ?? `${fallback} ${company.tax_id}`;
}

/**
 * Topbar company switcher. Selecting a company updates the active-company store
 * (persisted to localStorage), re-scoping the offers view and dashboard cards.
 */
export function CompanySwitcher() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { companies, activeCompany, setActiveCompany } = useActiveCompany();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (companies.length === 0) {
    return (
      <Button size="sm" variant="outline" onClick={() => navigate("/companies/new/1")}>
        {t("companies.create")}
      </Button>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="flex max-w-[220px] items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium text-text transition-colors hover:bg-surface-2"
      >
        <span className="truncate">
          {activeCompany ? companyLabel(activeCompany, t("companies.noName")) : t("home.activeCompany")}
        </span>
        <ChevronDown size={14} strokeWidth={1.75} aria-hidden="true" />
      </button>

      {open ? (
        <ul
          role="listbox"
          className="absolute right-0 z-30 mt-1 max-h-80 w-72 overflow-auto rounded-md border border-border bg-surface p-1 shadow-lg animate-fade-in"
        >
          {companies.map((company) => {
            const isActive = company.id === activeCompany?.id;
            return (
              <li key={company.id} role="option" aria-selected={isActive}>
                <button
                  type="button"
                  onClick={() => {
                    setActiveCompany(company.id);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded px-2.5 py-2 text-left text-sm hover:bg-surface-2",
                    isActive && "bg-brand-soft",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate text-text">
                    {companyLabel(company, t("companies.noName"))}
                  </span>
                  <CompanyStatusBadge status={company.status} />
                </button>
              </li>
            );
          })}
          <li className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                void navigate("/companies/new/1");
              }}
              className="w-full rounded px-2.5 py-2 text-left text-sm font-medium text-brand hover:bg-surface-2"
            >
              + {t("companies.create")}
            </button>
          </li>
        </ul>
      ) : null}
    </div>
  );
}
