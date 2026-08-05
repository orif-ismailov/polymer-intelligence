import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";


import { cn, formatDateTime } from "@/shared/lib";
import { Alert, Button, Input, PaperclipIcon, Spinner } from "@/shared/ui";

/** One chat line, in the shape every thread endpoint already returns. */
export interface ThreadMessage {
  id: number;
  author_company_id: number;
  body: string;
  has_file: boolean;
  file_name: string | null;
  created_at: string;
}

export interface ThreadChatProps {
  companyId: number;
  threadId: number;
  /**
   * The three calls a thread needs. Passed in rather than imported so one
   * component serves every conversation surface — the alternative is a copy per
   * domain, and the copies drift: this file already existed twice (manufacturer
   * and logistics) before it existed once.
   */
  api: {
    messages: (
      threadId: number,
      companyId: number,
      afterId?: number | null,
    ) => Promise<{ items: ThreadMessage[]; last_id: number | null }>;
    postMessage: (
      threadId: number,
      companyId: number,
      body: string,
      file?: File | null,
    ) => Promise<ThreadMessage>;
    messageFileUrl: (
      threadId: number,
      messageId: number,
      companyId: number,
    ) => Promise<{ url: string }>;
  };
  /** Poll cadence; every existing chat uses 15 s. */
  pollMs?: number;
}

/**
 * A two-party conversation, for any thread-shaped endpoint.
 *
 * Polls with `after_id`, so a long conversation costs one small delta per tick —
 * safe only because every one of these tables is append-only server-side.
 *
 * The cursor lives in a REF, not state: the poll closure has to read the newest
 * value without the interval being torn down and rebuilt on every message.
 *
 * "Mine" is derived here from `author_company_id === companyId`. None of the
 * APIs resolve it, because one thread is read from both sides.
 *
 * Nothing here decides who may read a thread — the backend refuses one the
 * caller is not a party to, which is what keeps a competitor's terms private.
 */
export function ThreadChat({
  companyId,
  threadId,
  api,
  pollMs = 15_000,
}: ThreadChatProps) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  // Kept in a ref, not state: the poll closure must read the newest cursor
  // without the interval being torn down and rebuilt on every message.
  const cursor = useRef<number | null>(null);
  // Callers build `api` inline, so it is a new object every render. Reading it
  // through a ref keeps the poll on the newest binding without the interval
  // being rebuilt (and the conversation reset to empty) on each parent render.
  const apiRef = useRef(api);
  apiRef.current = api;

  useEffect(() => {
    let cancelled = false;
    cursor.current = null;
    setMessages([]);
    setLoading(true);

    async function poll(): Promise<void> {
      try {
        const page = await apiRef.current.messages(threadId, companyId, cursor.current);
        if (cancelled) return;
        if (page.items.length > 0) {
          cursor.current = page.last_id ?? cursor.current;
          setMessages((prev) => [...prev, ...page.items]);
        }
        setError(null);
      } catch {
        if (!cancelled) setError(t("errors.loadFailed"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void poll();
    const timer = window.setInterval(() => void poll(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [companyId, threadId, pollMs, t]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length]);

  async function send(): Promise<void> {
    if (!text.trim() && !file) return;
    setSending(true);
    setError(null);
    try {
      const posted = await api.postMessage(threadId, companyId, text.trim(), file);
      cursor.current = posted.id;
      setMessages((prev) => [...prev, posted]);
      setText("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setSending(false);
    }
  }

  async function openAttachment(message: ThreadMessage): Promise<void> {
    const { url } = await api.messageFileUrl(
      threadId,
      message.id,
      companyId,
    );
    window.open(url, "_blank", "noopener");
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className="max-h-[28rem] min-h-[16rem] space-y-3 overflow-y-auto rounded-md border border-border bg-surface-inset p-3"
        role="log"
        aria-label={t("threadChat.title")}
      >
        {loading ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-subtle">
            {t("threadChat.empty")}
          </p>
        ) : (
          messages.map((message) => {
            const mine = message.author_company_id === companyId;
            return (
              <div key={message.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg border px-3 py-2",
                    mine
                      ? "border-brand-line bg-brand-soft text-text"
                      : "border-border bg-surface text-text",
                  )}
                >
                  {message.body ? (
                    <p className="whitespace-pre-wrap break-words text-sm">{message.body}</p>
                  ) : null}
                  {message.has_file ? (
                    <button
                      type="button"
                      onClick={() => void openAttachment(message)}
                      className="mt-1 inline-flex items-center gap-1.5 text-sm font-medium text-brand underline-offset-2 hover:underline"
                    >
                      <PaperclipIcon size={14} />
                      {message.file_name}
                    </button>
                  ) : null}
                  <p className="num mt-1 text-[11px] text-text-subtle">
                    {formatDateTime(message.created_at)}
                  </p>
                </div>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>

      {error ? <Alert tone="danger" title={error} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder={t("threadChat.placeholder")}
          aria-label={t("threadChat.placeholder")}
          className="min-w-0 flex-1"
        />
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept="application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={sending}>
          {file ? (
            <span className="inline-flex max-w-[12rem] items-center gap-1.5">
              <PaperclipIcon size={14} />
              <span className="truncate">{file.name}</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5">
              <PaperclipIcon size={14} />
              {t("threadChat.attach")}
            </span>
          )}
        </Button>
        <Button onClick={() => void send()} loading={sending} disabled={!text.trim() && !file}>
          {t("threadChat.send")}
        </Button>
      </div>
    </div>
  );
}
