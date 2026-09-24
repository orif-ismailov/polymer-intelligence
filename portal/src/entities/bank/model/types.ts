/** A branch from the Central Bank's register, looked up by its MFO. */
export interface BankBranch {
  /** The 5-digit «Код филиала» — the same value the bank step collects. */
  mfo: string;
  /** The parent bank, e.g. `ALOQABANK`. This is what the form fills in. */
  bank_name: string;
  /** The branch itself. Carried for context; nothing stores it today. */
  branch_name: string | null;
}
