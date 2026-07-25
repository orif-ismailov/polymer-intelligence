import { useState } from "react";

import { useTranslation } from "react-i18next";

import { Button } from "@/shared/ui";
import type { ButtonVariant } from "@/shared/ui";

import { EimzoSignDialog } from "./EimzoSignDialog";
import type { EimzoVerifyOut } from "../model/api";

interface EimzoSignButtonProps {
  companyId: number;
  onConfirmed?: (result: EimzoVerifyOut) => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  label?: string;
}

/** Button + controlled E-IMZO dialog for an already-created company (status/detail screens). */
export function EimzoSignButton({
  companyId,
  onConfirmed,
  variant = "secondary",
  disabled,
  label,
}: EimzoSignButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        variant={variant}
        disabled={disabled}
        onClick={() => setOpen(true)}
        data-testid="eimzo-open"
      >
        {label ?? t("eimzo.cta")}
      </Button>
      <EimzoSignDialog
        open={open}
        companyId={open ? companyId : null}
        onClose={() => setOpen(false)}
        onConfirmed={onConfirmed}
      />
    </>
  );
}
