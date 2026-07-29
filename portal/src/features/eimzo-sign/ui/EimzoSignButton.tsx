import { useState } from "react";

import { useTranslation } from "react-i18next";

import { Button } from "@/shared/ui";
import type { ButtonVariant } from "@/shared/ui";

import { EimzoSignDialog } from "./EimzoSignDialog";
import type { EimzoSigner } from "../model/useEimzoSign";

interface EimzoSignButtonProps<T> {
  signer: EimzoSigner<T>;
  onConfirmed?: (data: T) => void;
  holderOf?: (data: T) => string | null | undefined;
  variant?: ButtonVariant;
  disabled?: boolean;
  label?: string;
}

/** Button + controlled E-IMZO dialog bound to a signer (status screens, contract sign). */
export function EimzoSignButton<T>({
  signer,
  onConfirmed,
  holderOf,
  variant = "secondary",
  disabled,
  label,
}: EimzoSignButtonProps<T>) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button variant={variant} disabled={disabled} onClick={() => setOpen(true)} data-testid="eimzo-open">
        {label ?? t("eimzo.cta")}
      </Button>
      <EimzoSignDialog
        open={open}
        signer={open ? signer : null}
        onClose={() => setOpen(false)}
        onConfirmed={onConfirmed}
        holderOf={holderOf}
      />
    </>
  );
}
