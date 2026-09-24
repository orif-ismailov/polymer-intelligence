interface PaginationProps {
  offset: number;
  total: number;
  pageSize: number;
  onChange: (offset: number) => void;
  /** Accessible name of the `<nav>`. */
  label: string;
  prevLabel: string;
  nextLabel: string;
  /** «Страница 2 из 5» — the caller formats it, this primitive has no i18n. */
  pageOfLabel: (page: number, pages: number) => string;
}

const BUTTON =
  "inline-flex h-11 items-center rounded-md border border-border-strong px-4 text-sm font-medium text-text transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:text-text-subtle disabled:hover:bg-transparent";

/**
 * Prev / «page N of M» / next over an offset-paged list. Renders nothing when
 * everything fits on one page.
 *
 * The end is computed from the REAL total, never guessed from a short page.
 * This markup lived inline in the market and directory pages before a third
 * catalog needed it.
 */
export function Pagination({
  offset,
  total,
  pageSize,
  onChange,
  label,
  prevLabel,
  nextLabel,
  pageOfLabel,
}: PaginationProps) {
  if (total <= pageSize) return null;
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav aria-label={label} className="mt-8 flex items-center justify-between gap-4">
      <button
        type="button"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - pageSize))}
        className={BUTTON}
      >
        {prevLabel}
      </button>
      <span className="num text-sm text-text-muted">{pageOfLabel(page, pages)}</span>
      <button
        type="button"
        disabled={offset + pageSize >= total}
        onClick={() => onChange(offset + pageSize)}
        className={BUTTON}
      >
        {nextLabel}
      </button>
    </nav>
  );
}
