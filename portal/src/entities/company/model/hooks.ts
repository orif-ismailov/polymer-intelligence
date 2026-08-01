import { useEffect } from "react";

import { useQuery } from "@tanstack/react-query";

import { companyApi, companyKeys } from "./api";
import { useActiveCompanyStore } from "./activeCompanyStore";
import type { CompanyDetail, CompanySummary } from "./types";

/**
 * List all companies the account is a member of.
 *
 * `enabled` exists for the storefront. `/market/:id` and `/{directory}/:id`
 * render for anonymous visitors and are server-rendered, so an unguarded
 * `GET /portal/companies` would fire once from Node during every SSR render and
 * again in every anonymous browser — a guaranteed 401 either way. Cabinet
 * callers sit behind `RequireAuth` and want the default.
 */
export function useCompanies(enabled = true) {
  return useQuery<CompanySummary[]>({
    queryKey: companyKeys.list(),
    queryFn: () => companyApi.list(),
    enabled,
  });
}

/** Fetch a single company's full detail. */
export function useCompany(id: number | null) {
  return useQuery<CompanyDetail>({
    queryKey: companyKeys.detail(id ?? -1),
    queryFn: () => companyApi.get(id as number),
    enabled: id != null,
  });
}

/**
 * Resolve the "active" company, self-healing the stored selection: if none is
 * chosen (or the stored id no longer exists), it defaults to the first company.
 */
export function useActiveCompany(enabled = true) {
  const companiesQuery = useCompanies(enabled);
  const activeCompanyId = useActiveCompanyStore((s) => s.activeCompanyId);
  const setActiveCompany = useActiveCompanyStore((s) => s.setActiveCompany);

  const companies = companiesQuery.data;

  useEffect(() => {
    if (!companies) return;
    if (companies.length === 0) {
      if (activeCompanyId !== null) setActiveCompany(null);
      return;
    }
    const exists = companies.some((c) => c.id === activeCompanyId);
    if (!exists) {
      setActiveCompany(companies[0]?.id ?? null);
    }
  }, [companies, activeCompanyId, setActiveCompany]);

  const active =
    companies?.find((c) => c.id === activeCompanyId) ?? companies?.[0] ?? null;

  return {
    activeCompanyId: active?.id ?? null,
    activeCompany: active,
    companies: companies ?? [],
    isLoading: companiesQuery.isLoading,
    isError: companiesQuery.isError,
    refetch: companiesQuery.refetch,
    setActiveCompany,
  };
}
