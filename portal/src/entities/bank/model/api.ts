import { api } from "@/shared/api";

import type { BankBranch } from "./types";

export const bankApi = {
  /**
   * The bank behind a 5-digit MFO.
   *
   * 404 is an ordinary answer: the register is a dated snapshot of the CB's list,
   * so a branch it has not caught up with must still be registrable. Callers
   * treat a miss as "leave the field alone", never as an error.
   */
  byMfo: (mfo: string): Promise<BankBranch> =>
    api.get<BankBranch>(`/portal/reference/banks/${mfo}`),
};

export const bankKeys = {
  byMfo: (mfo: string) => ["bank", mfo] as const,
};
