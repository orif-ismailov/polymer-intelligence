"use client";

/**
 * One area of the project settings (/admin/settings/<module>)
 *
 * Every switch in this area, what it is running, and what `.env` says — side by
 * side, with the env var named and a way back.
 *
 * The pairing is the whole design. Until this screen existed, changing a switch
 * meant an SSH session and a restart, and the previous attempt at making them
 * editable stored a value next to a default written in Python, so a fresh
 * database ran on something nobody could see. On 31.08.2026 that turned a
 * healthy Didox integration into a 503 for a day. Here a row with no override
 * shows the `.env` value and says so; a row with one says who changed it and
 * offers Reset. Neither state is ambiguous, which is the property that was
 * missing.
 *
 * ONE PAGE PER AREA, and the area is `SettingSpec.group` from the backend. This
 * was a single scroll of thirty rows until the sidebar grew a Настройки проекта
 * group; splitting it means the menu entry names what you are looking at, so the
 * page needs no section headings of its own.
 *
 * The endpoint is not split — `GET /admin/settings` still returns all thirty and
 * this filters. That keeps the query key shared, so a write in one area
 * refreshes the others: `gov_registry_mode` and `didox_partner_token` are
 * validated against each other on the server, and they live on the same page,
 * but nothing stops a future pair from not doing so.
 *
 * Two gates, matching the API: `appSettings:write` to change anything, plus
 * administrator for the two credentials — see backend app/api/admin_settings.py.
 *
 * No hardcoded hex.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Settings2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { NewsPromptEditor } from "@/components/admin/NewsPromptEditor";
import { RouteGuardFallback } from "@/components/shared/RouteGuardFallback";
import { Button } from "@/components/ui/button";
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
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";
import { SETTINGS_MODULES } from "@/lib/nav";
import { formatTashkent } from "@/lib/tz";

// ─── Types ─────────────────────────────────────────────────────────────────────

type SettingValue = boolean | number | string | null;

interface SettingItem {
  key: string;
  label: string;
  group: string;
  value: SettingValue;
  env_value: SettingValue;
  env_var: string;
  overridden: boolean;
  overridden_by: string | null;
  overridden_at: string | null;
  editable: boolean;
  sensitive: boolean;
  /** Non-empty → make the operator confirm, and this sentence says why. */
  confirm: string;
  kind: "bool" | "int" | "float" | "choice" | "str";
  choices: string[];
}

/** A change waiting on the confirmation dialog. */
interface PendingChange {
  item: SettingItem;
  value: SettingValue;
}

const inputCls =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent";

/**
 * The reader's name and explanation for one setting.
 *
 * The backend's `label` is written for whoever maintains `Settings` — "Escrow
 * rail: stub (an operator confirms movement) or live (bank adapter)" tells you
 * the shape of the union, not what happens to money. These strings answer the
 * operator's question instead: what does this do, and what changes if I touch it.
 *
 * `label` stays as the fallback rather than the source. A switch added to the
 * backend catalog before anyone has translated it then still renders — in
 * English, which is worse than Russian and much better than a raw message key.
 * `backend/tests/test_settings_translations.py` fails when that gap opens, so
 * the fallback is a safety net rather than somewhere strings quietly live.
 */
function useSettingText(): (item: SettingItem) => { name: string; desc: string | null } {
  const t = useTranslations("adminSettings");
  return (item) => ({
    name: t.has(`items.${item.key}.name`) ? t(`items.${item.key}.name`) : item.label,
    desc: t.has(`items.${item.key}.desc`) ? t(`items.${item.key}.desc`) : null,
  });
}

/** Render a value for the "from .env" line. Empty is a fact worth stating. */
function display(value: SettingValue, empty: string): string {
  if (value === null || value === "") return empty;
  return String(value);
}

/**
 * Whether this change should stop and ask first.
 *
 * A `confirm` sentence means the switch has a consequence that outlives the
 * click. For the numeric ones it is directional — shortening a contract TTL
 * retires contracts, lengthening it does nothing — so only the harmful
 * direction interrupts. Asking on a harmless change is how people learn to
 * click through the dialog that matters.
 */
function needsConfirm(item: SettingItem, next: SettingValue): boolean {
  if (!item.confirm) return false;
  if (item.kind === "int" || item.kind === "float") {
    return Number(next) < Number(item.value);
  }
  return true;
}

// ─── Row ───────────────────────────────────────────────────────────────────────

function SettingRow({
  item,
  canWrite,
  isAdmin,
  busy,
  onChange,
  onReset,
}: {
  item: SettingItem;
  canWrite: boolean;
  isAdmin: boolean;
  busy: boolean;
  onChange: (item: SettingItem, value: SettingValue) => void;
  onReset: (item: SettingItem) => void;
}) {
  const t = useTranslations("adminSettings");
  const { name, desc } = useSettingText()(item);

  // `null` means "not editing", and the field shows what the server says. A
  // draft exists only while the operator is mid-edit, so a background refetch
  // cannot overwrite what they are typing — and there is no effect syncing the
  // two, because the displayed value is derived rather than stored.
  const [draft, setDraft] = useState<string | null>(null);
  const dirty = draft !== null;
  // A secret's `value` is the MASK (`••••-dev`), so putting it in the field would
  // make an operator who edits rather than replaces submit `••••-devsk-ant-…`.
  // The mask is the placeholder (below) and the field starts empty, so whatever
  // is typed is exactly what is sent. Only `anthropic_api_key` is checked with
  // its provider; the two Didox credentials would have stored the mangled string.
  const shown = draft ?? (item.sensitive || item.value === null ? "" : String(item.value));

  const locked = !item.editable || !canWrite || (item.sensitive && !isAdmin);
  const lockReason = !item.editable
    ? t("envOnly")
    : item.sensitive && !isAdmin && canWrite
      ? t("adminOnly")
      : "";

  const commit = (value: SettingValue) => {
    setDraft(null);
    onChange(item, value);
  };

  return (
    <li className="flex flex-col gap-3 py-4 md:flex-row md:items-start md:justify-between md:gap-6">
      <div className="min-w-0 md:flex-1">
        <p className="text-sm font-medium text-foreground">{name}</p>
        <code className="text-xs text-foreground-muted">{item.env_var}</code>
        {desc && (
          <p className="mt-1 max-w-prose text-xs leading-relaxed text-foreground-muted">{desc}</p>
        )}
        <p className="mt-1 text-xs text-foreground-muted">
          {item.overridden ? (
            <>
              <span className="text-accent">{t("overridden")}</span>
              {" — "}
              {t("envSays", { value: display(item.env_value, t("notSet")) })}
              {item.overridden_by ? ` · ${item.overridden_by}` : ""}
              {item.overridden_at ? ` · ${formatTashkent(item.overridden_at)}` : ""}
            </>
          ) : (
            t("fromEnv")
          )}
        </p>
        {lockReason && (
          <p className="mt-1 text-xs text-foreground-muted">{lockReason}</p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2 md:w-96 md:justify-end">
        {item.kind === "bool" ? (
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={Boolean(item.value)}
              disabled={locked || busy}
              onChange={(e) => commit(e.target.checked)}
            />
            {String(Boolean(item.value))}
          </label>
        ) : item.kind === "choice" ? (
          <select
            className={inputCls}
            value={String(item.value ?? "")}
            disabled={locked || busy}
            onChange={(e) => commit(e.target.value)}
          >
            {item.choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        ) : (
          <>
            <input
              className={inputCls}
              type={item.sensitive ? "password" : item.kind === "str" ? "text" : "number"}
              value={shown}
              placeholder={item.sensitive ? display(item.value, t("notSet")) : ""}
              disabled={locked || busy}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && dirty) commit(shown === "" ? null : shown);
              }}
            />
            {dirty && (
              <Button size="sm" disabled={busy} onClick={() => commit(shown === "" ? null : shown)}>
                {t("save")}
              </Button>
            )}
          </>
        )}

        <Button
          variant="ghost"
          size="sm"
          title={t("reset")}
          aria-label={t("reset")}
          disabled={locked || busy || !item.overridden}
          onClick={() => onReset(item)}
        >
          <RotateCcw className="size-4" />
        </Button>
      </div>
    </li>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function AdminSettingsModulePage() {
  const t = useTranslations("adminSettings");
  const router = useRouter();
  const qc = useQueryClient();
  const settingText = useSettingText();
  const params = useParams<{ module: string }>();
  const { user, isAdmin, isAuthenticated, can } = useAuth();

  // Not `module` — Next forbids assigning that identifier in a client bundle.
  const area = params.module;
  const known = SETTINGS_MODULES.includes(area);

  const canRead = isAdmin || can("appSettings", "read");
  const canWrite = isAdmin || can("appSettings", "write");

  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingChange | null>(null);

  useEffect(() => {
    if (isAuthenticated && user && !canRead) router.replace("/");
  }, [isAuthenticated, user, canRead, router]);

  // A module the nav does not know about is a stale link, not an empty area —
  // send the reader somewhere real rather than showing them nothing and letting
  // them conclude the settings are gone.
  useEffect(() => {
    if (!known) router.replace("/admin/settings/news");
  }, [known, router]);

  const settings = useQuery<SettingItem[]>({
    queryKey: ["admin-settings"],
    queryFn: () => apiFetch<SettingItem[]>("/admin/settings"),
    enabled: canRead,
  });

  const describeError = (e: unknown, fallback: string): string => {
    if (e instanceof ApiError) {
      const detail = (e.body as { detail?: unknown })?.detail;
      if (typeof detail === "string") return detail;
    }
    return fallback;
  };

  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: SettingValue }) =>
      apiFetch<SettingItem[]>(`/admin/settings/${key}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setError(null);
    },
    // The backend's 400 already says exactly what was wrong and names the field
    // — "DIDOX_PARTNER_TOKEN is required when GOV_REGISTRY_MODE=didox" is more
    // use than anything this layer could invent, so show it verbatim.
    onError: (e) => setError(describeError(e, t("saveError"))),
  });

  const reset = useMutation({
    mutationFn: (key: string) =>
      apiFetch<SettingItem[]>(`/admin/settings/${key}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-settings"] });
      setError(null);
    },
    onError: (e) => setError(describeError(e, t("resetError"))),
  });

  const busy = save.isPending || reset.isPending;

  // The endpoint returns every setting; this page shows one area of it.
  const items = useMemo(
    () => (settings.data ?? []).filter((item) => item.group === area),
    [settings.data, area],
  );

  const handleChange = (item: SettingItem, value: SettingValue) => {
    if (needsConfirm(item, value)) {
      setPending({ item, value });
      return;
    }
    save.mutate({ key: item.key, value });
  };

  // Effect-driven redirects take a beat, and a blank viewport during one reads
  // as a crash rather than as a bounce.
  if (user && !canRead) return <RouteGuardFallback />;
  if (!known) return <RouteGuardFallback />;

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex items-start gap-3">
        <Settings2 className="mt-1 size-5 text-foreground-muted" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {t.has(`groups.${area}`) ? t(`groups.${area}`) : t("title")}
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-foreground-muted">{t("subtitle")}</p>
        </div>
      </header>

      {!canWrite && (
        <p className="rounded-md border border-border bg-background-secondary p-3 text-sm text-foreground-muted">
          {t("readOnly")}
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400"
        >
          {error}
        </p>
      )}

      {settings.isError && <p className="text-sm text-red-400">{t("error")}</p>}
      {settings.isLoading && <p className="text-sm text-foreground-muted">{t("loading")}</p>}

      {/* The news area carries one thing the generic row cannot render: the
          prompt itself, which is kilobytes of text with its own version history.
          Mounted here rather than folded into the settings list so this page
          stays a list of switches. */}
      {area === "news" && !settings.isLoading && <NewsPromptEditor canWrite={canWrite} />}

      {items.length > 0 && (
        <section className="rounded-lg border border-border bg-background-secondary p-4">
          <ul className="flex flex-col divide-y divide-border">
            {items.map((item) => (
              <SettingRow
                key={item.key}
                item={item}
                canWrite={canWrite}
                isAdmin={isAdmin}
                busy={busy}
                onChange={handleChange}
                onReset={(target) => reset.mutate(target.key)}
              />
            ))}
          </ul>
        </section>
      )}

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending ? settingText(pending.item).name : ""}
            </AlertDialogTitle>
            <AlertDialogDescription>{pending?.item.confirm}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pending) save.mutate({ key: pending.item.key, value: pending.value });
                setPending(null);
              }}
            >
              {t("confirmAction")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
