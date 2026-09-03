"use client";

import { useTranslations } from "next-intl";
import { NAV_GROUPS, pageKeyOf, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** The three states a page can be in for one account. */
export type MatrixLevel = "none" | "read" | "write";

/** `{page: "read" | "write"}` — the wire shape. Absence means no access. */
export type AccessMap = Record<string, "read" | "write">;

export function levelOf(access: AccessMap, page: string): MatrixLevel {
  return access[page] ?? "none";
}

/**
 * The permission grid — one row per GRANT — grouped as the sidebar groups the nav.
 *
 * Laid out by nav group rather than alphabetically because the person granting
 * access is thinking about the product, not about a list of keys — they want
 * "everything under Заявки" to be one visual block, the way they see it.
 *
 * Rows are grants, not menu entries, and the two are no longer one-to-one: the
 * seven Настройки проекта screens share the `appSettings` page. A row that
 * stands for several screens is labelled by what is being granted rather than by
 * whichever screen happened to be first, because "Новости и отчёты" would be a
 * false description of a tick that also opens the Didox credentials.
 *
 * `adminOnly` items (staff administration) are not rendered: they are not
 * grantable, and showing a row that cannot be ticked invites the question of why.
 */
export function StaffAccessMatrix({
  value,
  onChange,
  disabled = false,
}: {
  value: AccessMap;
  onChange: (next: AccessMap) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("nav");
  const tAdmin = useTranslations("admin");

  function set(page: string, level: MatrixLevel) {
    const next = { ...value };
    // "none" is the ABSENCE of a key, not a stored value — the same shape the
    // backend persists, so the map can be sent as-is.
    if (level === "none") delete next[page];
    else next[page] = level;
    onChange(next);
  }

  const LEVELS: MatrixLevel[] = ["none", "read", "write"];

  /** What to call a row: the grant when it covers several screens, else the screen. */
  function labelFor(item: NavItem): string {
    return item.page ? t(`pages.${item.page}`) : t(`items.${item.key}`);
  }

  return (
    <div className={cn("flex flex-col gap-5", disabled && "opacity-50")}>
      {NAV_GROUPS.map((group) => {
        // One row per GRANT, not per menu entry. Several items can share a page
        // key — the seven Настройки проекта screens all grant `appSettings` —
        // and rendering one control each would put several radio groups over a
        // single stored value: they would disagree on screen, the last click
        // would win, and nothing would say so. Deduping keeps the matrix a
        // picture of what is actually stored.
        const seen = new Set<string>();
        const items = group.items.filter((i) => {
          if (i.adminOnly) return false;
          const page = pageKeyOf(i);
          if (seen.has(page)) return false;
          seen.add(page);
          return true;
        });
        if (items.length === 0) return null;
        return (
          <fieldset key={group.key} className="flex flex-col gap-1" disabled={disabled}>
            <legend className="mb-1 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
              {t(`groups.${group.key}`)}
            </legend>
            {items.map((item) => {
              const page = pageKeyOf(item);
              const label = labelFor(item);
              const current = levelOf(value, page);
              return (
                <div
                  key={page}
                  className="flex items-center justify-between gap-4 rounded-md px-2 py-1.5 hover:bg-background-tertiary"
                >
                  <span className="truncate text-sm text-foreground">{label}</span>
                  <div
                    role="radiogroup"
                    aria-label={label}
                    className="flex shrink-0 overflow-hidden rounded-md border border-border"
                  >
                    {LEVELS.map((level) => (
                      <button
                        key={level}
                        type="button"
                        role="radio"
                        aria-checked={current === level}
                        disabled={disabled}
                        onClick={() => set(page, level)}
                        className={cn(
                          "px-2.5 py-1 text-xs font-medium transition-colors",
                          current === level
                            ? "bg-accent text-background"
                            : "text-foreground-muted hover:bg-background-tertiary",
                        )}
                      >
                        {tAdmin(`access.${level}`)}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </fieldset>
        );
      })}
    </div>
  );
}
