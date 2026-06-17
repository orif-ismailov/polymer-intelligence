"use client";

/**
 * RequestActions — team action buttons in the request detail panel.
 *
 * Actions (D-10/D-11/D-12):
 *   - Contact Buyer: POST /requests/{id}/contact then open tg:// deep-link.
 *     Disabled with tooltip "No Telegram ID on file" when contact_available=false (Pitfall 6).
 *   - Add Note: inline 4-row textarea + "Save Note" → POST /requests/{id}/note.
 *   - Status dropdown: Select → PATCH /requests/{id} with new status.
 *     AlertDialog confirmation when transitioning to "cancelled".
 *   - Assign Owner: Select populated from GET /admin/users → POST /requests/{id}/assign.
 *   - Mark as Processed: → PATCH status=closed.
 *
 * All mutations use useMutation then invalidate ['request', id] + ['requests'].
 * Error copy from UI-SPEC Copywriting Contract.
 * No hardcoded hex — token classes only.
 */

import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2 } from "lucide-react";

import { apiFetch } from "@/lib/api";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const STATUS_OPTIONS = [
  { value: "viewed", label: "Viewed" },
  { value: "in_progress", label: "In Progress" },
  { value: "offer_sent", label: "Offer Sent" },
  { value: "matched", label: "Matched" },
  { value: "closed", label: "Closed" },
  { value: "cancelled", label: "Cancelled" },
];

interface StaffUserItem {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface RequestActionsProps {
  requestId: number;
  status: string;
  contactAvailable: boolean;
  assignedTo: number | null;
}

export function RequestActions({
  requestId,
  status,
  contactAvailable,
  assignedTo,
}: RequestActionsProps) {
  const queryClient = useQueryClient();

  const [noteText, setNoteText] = useState("");
  const [showNoteForm, setShowNoteForm] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState(status);
  const [actionError, setActionError] = useState<string | null>(null);

  // Fetch staff users for Assign Owner dropdown
  const { data: staffUsers } = useQuery<StaffUserItem[]>({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<StaffUserItem[]>("/admin/users"),
    staleTime: 5 * 60 * 1000, // 5 min
  });

  const invalidateRequest = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["request", String(requestId)] });
    queryClient.invalidateQueries({ queryKey: ["requests"] });
  }, [queryClient, requestId]);

  // Contact Buyer mutation
  const contactMutation = useMutation({
    mutationFn: () =>
      apiFetch<{ contact_available: boolean; tg_link: string }>(
        `/requests/${requestId}/contact`,
        { method: "POST" },
      ),
    onSuccess: (data) => {
      invalidateRequest();
      // Open tg:// deep-link
      if (data.tg_link) {
        window.open(data.tg_link, "_blank", "noopener,noreferrer");
      }
    },
    onError: () => {
      setActionError(
        "Status change failed. Refresh the page and try again.",
      );
    },
  });

  // Add note mutation
  const noteMutation = useMutation({
    mutationFn: (note: string) =>
      apiFetch(`/requests/${requestId}/note`, {
        method: "POST",
        body: JSON.stringify({ note }),
      }),
    onSuccess: () => {
      setNoteText("");
      setShowNoteForm(false);
      invalidateRequest();
    },
    onError: () => {
      setActionError(
        "Note could not be saved. Check your connection and try again.",
      );
    },
  });

  // Status change mutation (via PATCH)
  const statusMutation = useMutation({
    mutationFn: (newStatus: string) =>
      apiFetch(`/requests/${requestId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      }),
    onSuccess: () => {
      invalidateRequest();
    },
    onError: () => {
      setActionError(
        "Status change failed. Refresh the page and try again.",
      );
      setSelectedStatus(status); // revert optimistic
    },
  });

  // Assign owner mutation
  const assignMutation = useMutation({
    mutationFn: (staffUserId: number) =>
      apiFetch(`/requests/${requestId}/assign`, {
        method: "POST",
        body: JSON.stringify({ assigned_to: staffUserId }),
      }),
    onSuccess: () => {
      invalidateRequest();
    },
    onError: () => {
      setActionError(
        "Status change failed. Refresh the page and try again.",
      );
    },
  });

  // Mark as Processed (status=closed)
  const processedMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/requests/${requestId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "closed" }),
      }),
    onSuccess: () => {
      invalidateRequest();
    },
    onError: () => {
      setActionError(
        "Status change failed. Refresh the page and try again.",
      );
    },
  });

  const handleStatusChange = useCallback(
    (newStatus: string) => {
      setSelectedStatus(newStatus);
      if (newStatus !== "cancelled") {
        statusMutation.mutate(newStatus);
      }
      // "cancelled" is handled by AlertDialog confirm
    },
    [statusMutation],
  );

  const handleConfirmCancel = useCallback(() => {
    statusMutation.mutate("cancelled");
  }, [statusMutation]);

  const isAnyLoading =
    contactMutation.isPending ||
    noteMutation.isPending ||
    statusMutation.isPending ||
    assignMutation.isPending ||
    processedMutation.isPending;

  return (
    <div className="flex flex-col gap-4">
      {/* Error banner */}
      {actionError && (
        <div
          className="rounded-lg bg-urgency-high/10 border border-urgency-high/30 px-3 py-2"
          role="alert"
        >
          <p className="text-xs text-urgency-high">{actionError}</p>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="mt-1 text-xs text-urgency-high underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Contact Buyer — primary CTA (D-11) */}
      <TooltipProvider>
        {contactAvailable ? (
          <button
            type="button"
            onClick={() => contactMutation.mutate()}
            disabled={isAnyLoading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background-secondary"
          >
            {contactMutation.isPending ? (
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            ) : (
              <ExternalLink size={16} aria-hidden="true" />
            )}
            Contact Buyer
          </button>
        ) : (
          <Tooltip>
            <TooltipTrigger>
              <span className="block w-full">
                <button
                  type="button"
                  disabled
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-accent/30 px-4 py-2 text-sm font-medium text-white/50 cursor-not-allowed"
                  aria-disabled="true"
                >
                  <ExternalLink size={16} aria-hidden="true" />
                  Contact Buyer
                </button>
              </span>
            </TooltipTrigger>
            <TooltipContent>No Telegram ID on file</TooltipContent>
          </Tooltip>
        )}
      </TooltipProvider>

      {/* Add Note */}
      <div className="flex flex-col gap-2">
        {!showNoteForm ? (
          <button
            type="button"
            onClick={() => setShowNoteForm(true)}
            disabled={isAnyLoading}
            className="inline-flex w-full items-center justify-center rounded-lg border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background-secondary"
          >
            Add Note
          </button>
        ) : (
          <>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              rows={4}
              placeholder="Enter team note (not visible to client)…"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-foreground-subtle resize-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background-secondary"
              aria-label="Add note"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => noteMutation.mutate(noteText)}
                disabled={!noteText.trim() || noteMutation.isPending}
                className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {noteMutation.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Save Note
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowNoteForm(false);
                  setNoteText("");
                }}
                className="inline-flex items-center justify-center rounded-lg border border-border px-3 py-1.5 text-sm text-foreground hover:bg-background-tertiary transition-colors"
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </div>

      {/* Status dropdown with AlertDialog for cancelled */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`status-select-${requestId}`}
          className="text-xs text-foreground-muted"
        >
          Status
        </label>
        <AlertDialog>
          <div className="relative">
            <select
              id={`status-select-${requestId}`}
              value={selectedStatus}
              onChange={(e) => {
                const val = e.target.value;
                if (val === "cancelled") {
                  // Will be confirmed by AlertDialog
                  setSelectedStatus("cancelled");
                } else {
                  handleStatusChange(val);
                }
              }}
              disabled={isAnyLoading}
              className="w-full h-8 rounded-lg border border-border bg-background-secondary px-2.5 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {/* Cancel confirmation dialog */}
          {selectedStatus === "cancelled" && (
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Cancel this request?</AlertDialogTitle>
                <AlertDialogDescription>
                  Cancel this request? This cannot be undone. The buyer will not
                  be notified automatically.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel
                  onClick={() => setSelectedStatus(status)}
                >
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleConfirmCancel}
                  className="bg-red-500 text-white hover:bg-red-600"
                >
                  Confirm
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          )}
        </AlertDialog>
      </div>

      {/* Assign Owner */}
      {staffUsers && staffUsers.length > 0 && (
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`assign-select-${requestId}`}
            className="text-xs text-foreground-muted"
          >
            Assign Owner
          </label>
          <select
            id={`assign-select-${requestId}`}
            value={assignedTo ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              if (val) {
                assignMutation.mutate(parseInt(val, 10));
              }
            }}
            disabled={isAnyLoading}
            className="w-full h-8 rounded-lg border border-border bg-background-secondary px-2.5 text-sm text-foreground appearance-none cursor-pointer hover:bg-background-tertiary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">Unassigned</option>
            {staffUsers.map((user) => (
              <option key={user.id} value={user.id}>
                {user.email} ({user.role})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Mark as Processed */}
      <button
        type="button"
        onClick={() => processedMutation.mutate()}
        disabled={isAnyLoading || status === "closed"}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground hover:bg-background-tertiary disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background-secondary"
      >
        {processedMutation.isPending && (
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        )}
        Mark as Processed
      </button>
    </div>
  );
}
