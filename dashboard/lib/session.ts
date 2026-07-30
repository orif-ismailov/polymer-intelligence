/**
 * Cross-tab session identity broadcast.
 *
 * The refresh cookie is shared by every tab in the browser, not scoped to one, so
 * signing in as a different user silently changes who the *other* open tabs are —
 * the next navigation or refresh re-authenticates them as the new identity with no
 * indication anything happened. That is inherent to cookie sessions; what was
 * missing was the warning. Tabs announce identity changes here so an open tab can
 * say "this session is no longer yours" instead of quietly becoming someone else.
 *
 * Best-effort by design: no BroadcastChannel (or a blocked one) simply means no
 * notice — never a broken dashboard.
 */

const CHANNEL_NAME = "polymer-dashboard-session";

export type SessionEvent =
  | { type: "signin"; userId: number }
  | { type: "signout" };

function openChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") {
    return null;
  }
  try {
    return new BroadcastChannel(CHANNEL_NAME);
  } catch {
    return null;
  }
}

/** Tell the other tabs in this browser that the session identity changed. */
export function announceSession(event: SessionEvent): void {
  const channel = openChannel();
  if (!channel) return;
  try {
    channel.postMessage(event);
  } finally {
    channel.close();
  }
}

/**
 * Subscribe to identity changes made in *other* tabs. Returns an unsubscribe fn.
 *
 * BroadcastChannel does not echo to the sender, so the tab that signed in never
 * warns itself.
 */
export function onSessionChange(handler: (event: SessionEvent) => void): () => void {
  const channel = openChannel();
  if (!channel) return () => {};
  const listener = (message: MessageEvent<SessionEvent>) => {
    const data = message.data;
    if (data?.type === "signin" || data?.type === "signout") handler(data);
  };
  channel.addEventListener("message", listener);
  return () => {
    channel.removeEventListener("message", listener);
    channel.close();
  };
}
