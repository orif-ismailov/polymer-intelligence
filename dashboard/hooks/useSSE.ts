"use client";

import { useEffect, useRef } from "react";
import { getToken } from "@/lib/api";

const MIN_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;
/** Polling fallback interval — 30 s (DEC-realtime-sse-not-websocket) */
const POLL_FALLBACK_MS = 30_000;

/**
 * useSSE — EventSource wrapper with exponential backoff reconnect and
 * a 30-second polling fallback.
 *
 * @param url       SSE endpoint URL (e.g. "/api/v1/feed/stream")
 * @param onMessage Callback invoked with each SSE event's `data` string,
 *                  or the literal string "poll" when the polling fallback fires.
 *
 * Pattern: RESEARCH.md Pattern 2 (lines 328–404).
 * Decision: DEC-realtime-sse-not-websocket — SSE only, no WebSocket.
 */
export function useSSE(url: string, onMessage: (data: string) => void) {
  const retryRef = useRef<number>(MIN_RETRY_MS);
  // Use a ref for onMessage to avoid re-subscribing on every render.
  // Updated via a layout effect so it stays current without triggering reconnects.
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let es: EventSource | null = null;
    let pollFallbackTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let mounted = true;

    function clearTimers() {
      if (pollFallbackTimer !== null) {
        clearTimeout(pollFallbackTimer);
        pollFallbackTimer = null;
      }
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function connect() {
      if (!mounted) return;

      // EventSource cannot set an Authorization header, so the access JWT is
      // passed as the access_token query param (backend get_current_staff_user_sse
      // accepts it). Read the token at connect time so reconnects pick up refreshes.
      const token = getToken();
      const sep = url.includes("?") ? "&" : "?";
      const fullUrl = token
        ? `${url}${sep}access_token=${encodeURIComponent(token)}`
        : url;

      es = new EventSource(fullUrl, { withCredentials: true });

      es.onmessage = (evt: MessageEvent) => {
        // SSE succeeded — reset backoff
        retryRef.current = MIN_RETRY_MS;
        clearTimers();
        onMessageRef.current(evt.data as string);
      };

      es.onerror = () => {
        es?.close();
        if (!mounted) return;

        // Start polling fallback: if reconnect doesn't succeed,
        // onMessage('poll') fires after POLL_FALLBACK_MS
        pollFallbackTimer = setTimeout(() => {
          if (mounted) {
            onMessageRef.current("poll");
          }
        }, POLL_FALLBACK_MS);

        // Reconnect with exponential backoff capped at MAX_RETRY_MS
        const delay = Math.min(retryRef.current, MAX_RETRY_MS);
        retryRef.current = Math.min(retryRef.current * 2, MAX_RETRY_MS);

        reconnectTimer = setTimeout(() => {
          clearTimers();
          connect();
        }, delay);
      };
    }

    connect();

    return () => {
      mounted = false;
      es?.close();
      clearTimers();
    };
  }, [url]);
}
