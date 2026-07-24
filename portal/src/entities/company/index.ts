export type {
  CompanySummary,
  CompanyDetail,
  CompanyRole,
  BankAccount,
  DocumentMeta,
  CreateCompanyPayload,
  CompanyProfilePatch,
  CreateBankAccountPayload,
} from "./model/types";
export { companyApi, companyKeys } from "./model/api";
export { useActiveCompanyStore } from "./model/activeCompanyStore";
export { useCompanies, useCompany, useActiveCompany } from "./model/hooks";
export {
  useUpdateCompanyProfile,
  useSetCompanyRoles,
  useAddBankAccount,
  useRemoveBankAccount,
  useUploadCompanyDocument,
  useRemoveCompanyDocument,
} from "./model/mutations";
export { CompanyStatusBadge } from "./ui/CompanyStatusBadge";
