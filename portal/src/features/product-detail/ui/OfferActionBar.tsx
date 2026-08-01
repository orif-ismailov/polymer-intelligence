import { type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib";
import {
  ContractSheetIcon,
  MessageIcon,
  ShieldIcon,
  StickyActionBar,
} from "@/shared/ui";

interface OfferActionBarProps {
  canAct: boolean;
  /** False when the seller opted out of RFQs — there is no message door at all. */
  acceptsRfq: boolean;
  acceptsEscrow: boolean;
  /**
   * Why the contract cell is off, when it is (null = it is on). Resolved by the
   * page: "not offered", "seller not verified" and "your company not verified"
   * are three different sentences, and only the page knows which applies.
   */
  contractBlockedReason: string | null;
  onMessage: () => void;
  onContract: () => void;
}

/**
 * The mockup's three-way sticky footer: message · contract · escrow.
 *
 * Each cell is a full-height tap target with a vertical hairline between them —
 * not three separate Buttons — so the bar reads as one control strip.
 *
 * Disabled reasons stay in `title` only. Rendering the long hint under the
 * label crushed the three cells into unreadable stacks on a phone.
 */
export function OfferActionBar({
  canAct,
  acceptsRfq,
  acceptsEscrow,
  contractBlockedReason,
  onMessage,
  onContract,
}: OfferActionBarProps) {
  const { t } = useTranslation();

  if (!canAct) return null;

  return (
    <StickyActionBar className="!p-0 md:!p-0 !bottom-0">
      <div
        className="flex w-full divide-x divide-border overflow-hidden rounded-md border border-border bg-surface md:rounded-lg"
        data-testid="product-detail-action-bar"
      >
        <ActionCell
          icon={<MessageIcon size={18} />}
          label={t("market.detail.messageSeller")}
          onClick={onMessage}
          disabled={!acceptsRfq}
          hint={acceptsRfq ? null : t("market.detail.rfqNotAccepted")}
        />
        <ActionCell
          icon={<ContractSheetIcon size={18} />}
          label={t("market.detail.requestContract")}
          onClick={onContract}
          disabled={contractBlockedReason != null}
          hint={contractBlockedReason}
        />
        <ActionCell
          icon={<ShieldIcon size={18} />}
          label={t("market.detail.escrow")}
          disabled
          hint={
            acceptsEscrow
              ? t("market.detail.escrowInDealHint")
              : t("market.detail.escrowNotOffered")
          }
        />
      </div>
    </StickyActionBar>
  );
}

function ActionCell({
  icon,
  label,
  onClick,
  disabled = false,
  hint = null,
}: {
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  /** Hover / long-press explanation — never inlined under the label. */
  hint?: string | null;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={hint ?? undefined}
      aria-label={hint ? `${label}. ${hint}` : label}
      className={cn(
        "flex min-h-[4.25rem] min-w-0 flex-1 flex-col items-center justify-center gap-1 px-1.5 py-2.5 text-center transition-colors sm:px-3 sm:py-3.5",
        disabled
          ? "cursor-not-allowed text-text-subtle"
          : "text-text hover:bg-surface-2 hover:text-brand",
      )}
    >
      <span className="shrink-0 text-current">{icon}</span>
      <span className="max-w-[7.5rem] text-[11px] font-medium leading-tight sm:max-w-none sm:text-xs sm:leading-snug">
        {label}
      </span>
    </button>
  );
}
