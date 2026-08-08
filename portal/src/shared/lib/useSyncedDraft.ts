import { useEffect, useState } from "react";

/**
 * Local draft for an input whose committed value lives in the URL.
 *
 * A bare `defaultValue` leaves the input showing stale text when the URL
 * changes underneath it — «Сбросить фильтры», back/forward — and the next
 * blur then silently re-applies the stale filter. The draft here re-syncs
 * whenever the committed value changes, while still letting the visitor
 * type freely between commits.
 */
export function useSyncedDraft(committed: string): [string, (value: string) => void] {
  const [draft, setDraft] = useState(committed);
  useEffect(() => {
    setDraft(committed);
  }, [committed]);
  return [draft, setDraft];
}
