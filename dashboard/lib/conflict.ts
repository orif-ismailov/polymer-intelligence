import { ApiError } from "@/lib/api";

/**
 * The status a moderation queue item was already in, when `err` is the backend's
 * 409 `already_moderated` — otherwise null.
 *
 * Approve and reject are separate endpoints over one queue item, so a decision can
 * lose a race with another moderator (or with the Telegram inline buttons). The
 * backend refuses the loser rather than letting two half-decisions merge; the UI's
 * job is to say which way it actually went and refetch the queue, because a bare
 * "409" tells a moderator nothing about what happened to the item they just acted on.
 */
export function alreadyModeratedStatus(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const detail = (err.body as { detail?: { code?: string; status?: string } } | null)
    ?.detail;
  if (detail?.code !== "already_moderated") return null;
  return detail.status ?? "unknown";
}
