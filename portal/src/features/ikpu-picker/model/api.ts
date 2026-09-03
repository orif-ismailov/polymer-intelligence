import { api } from "@/shared/api";

/**
 * ИКПУ lookup for the offer form (P7.a W9).
 *
 * The code chosen here ends up on every «Договор НК» and ЭСФ the offer backs, and
 * both reach my.soliq.uz.
 *
 * **`search` covers the company's OWN basket, not the tasnif directory** —
 * confirmed live: with one code bound, `search=вода` and `search=02201001` both
 * find it while `search=полиэтилен` and `search=ноутбук` return nothing. Didox's
 * partner API exposes no global directory search at all, so a seller who has not
 * yet declared a code cannot find it here by name. They take the code from
 * tasnif.soliq.uz and ADD it; from then on it is theirs and searchable.
 */

export interface IkpuPackage {
  code: string;
  name: string;
}

export interface IkpuRow {
  class_code: string;
  name: string | null;
  /** The ЭСФ `Origin`: 1 own production · 2 resale · 3 services · 4 not involved. */
  origin_id: number | null;
  origin_name: string | null;
  use_package: boolean;
  packages: IkpuPackage[];
}

export const ikpuApi = {
  search: (companyId: number, q: string): Promise<IkpuRow[]> =>
    api.get<IkpuRow[]>(
      `/portal/ikpu/search?company_id=${companyId}&q=${encodeURIComponent(q)}`,
    ),

  packages: (companyId: number, classCode: string): Promise<IkpuPackage[]> =>
    api.get<IkpuPackage[]>(
      `/portal/companies/${companyId}/ikpu/${encodeURIComponent(classCode)}/packages`,
    ),

  /**
   * Declare that this company deals in the code — a PREREQUISITE, not a nicety.
   *
   * Until a code is bound it does not exist as far as `search` is concerned, so
   * this is how a new code enters the picker at all.
   */
  bind: (companyId: number, classCode: string): Promise<void> =>
    api.post<void>(
      `/portal/companies/${companyId}/ikpu/${encodeURIComponent(classCode)}/bind`,
    ),
};
