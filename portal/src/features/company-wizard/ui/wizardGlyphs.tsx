import { type ReactNode } from "react";

import {
  BankIcon,
  BuyerIcon,
  FactoryIcon,
  FileIcon,
  FolderCheckIcon,
  PenLineIcon,
  ShieldAlertIcon,
  SupplierIcon,
  TaxIcon,
  TraderIcon,
} from "@/shared/ui";

/*
 * Glyph lookups stay module-private and are exposed as components: exporting the
 * maps themselves from a .tsx file breaks Fast Refresh (and fails the lint gate,
 * which runs at --max-warnings 0).
 */

const ACCOUNT_TYPE_GLYPHS: Record<string, ReactNode> = {
  buyer: <BuyerIcon size={22} />,
  supplier: <SupplierIcon size={22} />,
  manufacturer: <FactoryIcon size={22} />,
  trader: <TraderIcon size={22} />,
};

/**
 * Keyed by the backend `check_type`, so a check the API adds later renders with
 * the fallback sheet glyph rather than a hole in the row.
 */
const CHECK_GLYPHS: Record<string, ReactNode> = {
  tax_id_format: <TaxIcon size={18} />,
  eimzo_signature: <PenLineIcon size={18} />,
  documents_complete: <FolderCheckIcon size={18} />,
  bank_requisites: <BankIcon size={18} />,
  manual_kyb: <ShieldAlertIcon size={18} />,
};

/** Glyph for an account type on «Выберите тип аккаунта». */
export function AccountTypeGlyph({ type }: { type: string }) {
  return <>{ACCOUNT_TYPE_GLYPHS[type] ?? <FileIcon size={22} />}</>;
}

/** Glyph for a verification check on «Проверка компании». */
export function CheckGlyph({ type }: { type: string }) {
  return <>{CHECK_GLYPHS[type] ?? <FileIcon size={18} />}</>;
}
