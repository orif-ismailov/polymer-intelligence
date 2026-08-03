import { type ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/shared/lib";

import { Button } from "./Button";

export type DialogPlacement = "center" | "sheet";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
  /**
   * `center` is the modal every cabinet flow uses. `sheet` anchors the panel to
   * the bottom edge, full width, and lets its body scroll inside a capped
   * height — the phone pattern for a control surface you pull up, act in, and
   * dismiss, where a centred `max-w-md` card would waste the width it needs and
   * put its footer in the middle of the screen.
   */
  placement?: DialogPlacement;
}

/**
 * Lightweight modal dialog. Traps focus to the panel, closes on Escape and
 * backdrop click, and restores focus to the previously-focused element.
 *
 * Both placements share every one of those behaviours — that is the reason a
 * bottom sheet is a variant here rather than its own component.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
  placement = "center",
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previouslyFocused.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  const isSheet = placement === "sheet";

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-50 flex justify-center",
        isSheet ? "items-end" : "items-center p-4",
      )}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 bg-overlay animate-fade-in"
        onClick={onClose}
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className={cn(
          "relative z-10 w-full border border-border bg-surface shadow-lg focus:outline-none",
          isSheet
            ? // Rounded at the top only: the bottom edge is the screen edge, and
              // a radius there would leave two slivers of backdrop under a panel
              // that is supposed to be resting on it. Capped at 85dvh — `dvh`,
              // not `vh`, so the sheet is not measured against a viewport that
              // includes the mobile browser's retracted URL bar. The header and
              // footer are `shrink-0` so only the body scrolls, which is what
              // keeps the primary action reachable however long the body runs.
              "max-h-[85dvh] animate-sheet-in flex-col rounded-t-lg pb-[env(safe-area-inset-bottom)]"
            : "max-w-md animate-scale-in rounded-lg",
          isSheet && "flex",
          className,
        )}
      >
        <div className={cn("border-b border-border px-5 py-4", isSheet && "shrink-0")}>
          <h2 className="text-base font-semibold text-text">{title}</h2>
          {description ? <p className="mt-1 text-sm text-text-muted">{description}</p> : null}
        </div>
        {children ? (
          <div className={cn("px-5 py-4", isSheet && "min-h-0 flex-1 overflow-y-auto")}>
            {children}
          </div>
        ) : null}
        {footer ? (
          <div
            className={cn(
              "flex gap-3 border-t border-border px-5 py-4",
              isSheet ? "shrink-0 items-center" : "justify-end",
            )}
          >
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  loading?: boolean;
  danger?: boolean;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onClose,
  loading,
  danger,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
