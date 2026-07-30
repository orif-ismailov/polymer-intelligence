import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { DEAL_POLL_MS, dealApi } from "@/entities/deal";
import type { DealMessage } from "@/entities/deal";
import { cn, formatDateTime } from "@/shared/lib";
import { Alert, Button, Input, PaperclipIcon, Spinner } from "@/shared/ui";

interface DealChatProps {
  companyId: number;
  dealId: number;
}

/**
 * Trade Room chat.
 *
 * Polls every 15 s with `after_id`, so a long conversation costs one small
 * delta per tick rather than the whole history. Messages are append-only
 * server-side, which is what makes that safe: nothing already fetched can
 * change underneath us.
 */
export function DealChat({ companyId, dealId }: DealChatProps) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<DealMessage[]>([]);
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

  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      try {
        const page = await dealApi.messages(companyId, dealId, cursor.current);
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
    const timer = window.setInterval(() => void poll(), DEAL_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [companyId, dealId, t]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length]);

  async function send(): Promise<void> {
    if (!text.trim() && !file) return;
    setSending(true);
    setError(null);
    try {
      const posted = await dealApi.postMessage(companyId, dealId, text.trim(), file);
      // Append our own message straight away; the next poll starts after it.
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

  async function openAttachment(message: DealMessage): Promise<void> {
    const url = await dealApi.messageFileUrl(companyId, dealId, message.id);
    window.open(url, "_blank", "noopener");
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className="max-h-[28rem] min-h-[12rem] space-y-3 overflow-y-auto rounded-md border border-border bg-surface-inset p-3"
        role="log"
        aria-label={t("deals.chat.title")}
      >
        {loading ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : messages.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-subtle">{t("deals.chat.empty")}</p>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={cn("flex", message.mine ? "justify-end" : "justify-start")}
            >
              <div
                className={cn(
                  "max-w-[80%] rounded-lg border px-3 py-2",
                  message.mine
                    ? "border-brand-line bg-brand-soft text-text"
                    : "border-border bg-surface text-text",
                )}
              >
                {!message.mine ? (
                  <p className="mb-0.5 text-xs font-medium text-text-muted">
                    {message.author_company_name ?? "—"}
                  </p>
                ) : null}
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
          ))
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
          placeholder={t("deals.chat.placeholder")}
          aria-label={t("deals.chat.placeholder")}
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
              {t("deals.chat.attach")}
            </span>
          )}
        </Button>
        <Button onClick={() => void send()} loading={sending} disabled={!text.trim() && !file}>
          {t("deals.chat.send")}
        </Button>
      </div>
    </div>
  );
}
