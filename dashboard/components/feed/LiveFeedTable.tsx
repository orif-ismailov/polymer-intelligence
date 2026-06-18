"use client";

/**
 * LiveFeedTable — TanStack Table rendering of GET /api/v1/feed with keyset pagination.
 *
 * - useQuery(['feed', filters]) fetches from /api/v1/feed with all filter params
 * - useSSE('/api/v1/feed/stream', ...) calls queryClient.invalidateQueries on SSE events
 *   (DEC-realtime-sse-not-websocket: SSE + 30s polling fallback, no WebSocket)
 * - Keyset pagination via next_cursor_event_at / next_cursor_id (no OFFSET)
 * - Relative times wrapped in <time datetime={iso}> for accessibility
 * - All styling via token classes (no hardcoded hex) — T-04-08
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Activity, ChevronLeft, ChevronRight } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { useSSE } from "@/hooks/useSSE";
import { relativeTime } from "@/lib/tz";
import { KindChip } from "@/components/shared/KindChip";
import { UrgencyChip } from "@/components/shared/UrgencyChip";
import { StatusChip } from "@/components/shared/StatusChip";

/** FeedItem shape from app.schemas.dashboard (04-01). */
interface FeedItem {
  id: number;
  origin: string;
  kind: string;
  product_id: number | null;
  grade_text: string | null;
  volume: string | null;
  price: string | null;
  currency: string | null;
  region: string | null;
  urgency: string | null;
  status: string | null;
  event_at: string;
}

interface FeedPage {
  items: FeedItem[];
  next_cursor_event_at: string | null;
  next_cursor_id: number | null;
}

interface FeedFilters {
  period: string;
  kind: string;
  source: string;
  urgency: string;
  cursor_event_at?: string;
  cursor_id?: number;
}

function buildFeedUrl(filters: FeedFilters): string {
  const params = new URLSearchParams();
  params.set("period", filters.period || "30d");
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.source) params.set("source", filters.source);
  if (filters.urgency) params.set("urgency", filters.urgency);
  if (filters.cursor_event_at) params.set("cursor_event_at", filters.cursor_event_at);
  if (filters.cursor_id != null) params.set("cursor_id", String(filters.cursor_id));
  params.set("limit", "50");
  return `/feed?${params.toString()}`;
}

const columnHelper = createColumnHelper<FeedItem>();

const columns = [
  columnHelper.accessor("event_at", {
    header: "Time",
    cell: (info) => (
      <time
        dateTime={info.getValue()}
        className="text-sm text-foreground-muted whitespace-nowrap"
        title={info.getValue()}
      >
        {relativeTime(info.getValue())}
      </time>
    ),
  }),
  columnHelper.accessor("kind", {
    header: "Kind",
    cell: (info) => <KindChip kind={info.getValue()} />,
  }),
  columnHelper.accessor("grade_text", {
    header: "Product / Grade",
    cell: (info) => (
      <span className="text-sm text-foreground">
        {info.getValue() ?? "—"}
      </span>
    ),
  }),
  columnHelper.accessor("volume", {
    header: "Volume",
    cell: (info) => (
      <span className="text-sm font-mono text-foreground">
        {info.getValue() != null ? `${info.getValue()} MT` : "—"}
      </span>
    ),
  }),
  columnHelper.accessor("price", {
    header: "Price",
    cell: (info) => {
      const row = info.row.original;
      const price = info.getValue();
      const currency = row.currency ?? "USD";
      return (
        <span className="text-sm font-mono text-foreground">
          {price != null ? `${price} ${currency}/MT` : "—"}
        </span>
      );
    },
  }),
  columnHelper.accessor("region", {
    header: "Region",
    cell: (info) => (
      <span className="text-sm text-foreground">
        {info.getValue() ?? "—"}
      </span>
    ),
  }),
  columnHelper.accessor("urgency", {
    header: "Urgency",
    cell: (info) => {
      const urgency = info.getValue();
      return urgency ? <UrgencyChip urgency={urgency} /> : <span className="text-foreground-subtle">—</span>;
    },
  }),
  columnHelper.accessor("status", {
    header: "Status",
    cell: (info) => {
      const status = info.getValue();
      return status ? <StatusChip status={status} /> : <span className="text-foreground-subtle">—</span>;
    },
  }),
];

interface LiveFeedTableProps {
  /** Pre-set kind filter (for /offers page: "sell_offer") */
  defaultKind?: string;
  /** Number of rows shown in compact mode */
  compact?: boolean;
  className?: string;
}

export function LiveFeedTable({ defaultKind, compact = false, className = "" }: LiveFeedTableProps) {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const period = searchParams.get("period") ?? "30d";
  const kind = defaultKind ?? searchParams.get("kind") ?? "";
  const source = searchParams.get("source") ?? "";
  const urgency = searchParams.get("urgency") ?? "";

  // Keyset cursor stack for Prev/Next navigation
  const [cursorStack, setCursorStack] = useState<Array<{ event_at: string; id: number }>>([]);
  const currentCursor = cursorStack[cursorStack.length - 1];

  // WR-05: reset the cursor stack when any filter changes so we always start
  // from page 1 of the new result set, not a stale cursor from the previous one.
  const prevFiltersRef = useRef({ period, kind, source, urgency });
  useEffect(() => {
    const prev = prevFiltersRef.current;
    if (
      prev.period !== period ||
      prev.kind !== kind ||
      prev.source !== source ||
      prev.urgency !== urgency
    ) {
      setCursorStack([]);
      prevFiltersRef.current = { period, kind, source, urgency };
    }
  }, [period, kind, source, urgency]);

  const filters: FeedFilters = {
    period,
    kind,
    source,
    urgency,
    cursor_event_at: currentCursor?.event_at,
    cursor_id: currentCursor?.id,
  };

  // Query the feed — ['feed', filters] query key drives invalidation from SSE
  const { data, isLoading, isError, error } = useQuery<FeedPage>({
    queryKey: ["feed", filters],
    queryFn: () => apiFetch<FeedPage>(buildFeedUrl(filters)),
  });

  // Wire SSE: invalidate ['feed'] query on each new event (DEC-realtime-sse-not-websocket)
  const handleSSEMessage = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["feed"] });
  }, [queryClient]);

  useSSE("/api/v1/feed/stream", handleSSEMessage);

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const handleNext = () => {
    if (data?.next_cursor_event_at && data?.next_cursor_id != null) {
      setCursorStack((prev) => [
        ...prev,
        { event_at: data.next_cursor_event_at!, id: data.next_cursor_id! },
      ]);
    }
  };

  const handlePrev = () => {
    setCursorStack((prev) => prev.slice(0, -1));
  };

  const hasNext = !!(data?.next_cursor_event_at && data?.next_cursor_id != null);
  const hasPrev = cursorStack.length > 0;

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center py-12 ${className}`}>
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        <span className="ml-3 text-sm text-foreground-muted">Loading feed…</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={`rounded-lg bg-background-secondary border border-border p-6 ${className}`}>
        <p className="text-sm text-urgency-high">
          Failed to load feed: {error instanceof Error ? error.message : "Unknown error"}
        </p>
      </div>
    );
  }

  if (!data?.items.length) {
    return (
      <div className={`flex flex-col items-center justify-center gap-3 py-16 ${className}`}>
        <Activity size={32} className="text-foreground-muted" aria-hidden="true" />
        <p className="text-sm font-semibold text-foreground">No market activity yet</p>
        <p className="text-sm text-foreground-muted">
          Signals will appear here as sources report data.
        </p>
      </div>
    );
  }

  const displayRows = compact ? table.getRowModel().rows.slice(0, 10) : table.getRowModel().rows;

  return (
    <div className={`flex flex-col gap-4 ${className}`}>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm" role="grid" aria-label="Live market feed">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-border bg-background-secondary">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-4 py-3 text-left text-xs font-semibold text-foreground-muted uppercase tracking-wider"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {displayRows.map((row) => (
              <tr
                key={row.id}
                role="row"
                className="border-b border-border bg-background hover:bg-background-secondary transition-colors duration-150"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination controls — only in full (non-compact) mode */}
      {!compact && (
        <div className="flex items-center justify-between">
          <button
            onClick={handlePrev}
            disabled={!hasPrev}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background-secondary px-3 py-1.5 text-sm text-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-background-tertiary focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft size={16} />
            Prev
          </button>
          <span className="text-xs text-foreground-muted">
            {data.items.length} results
          </span>
          <button
            onClick={handleNext}
            disabled={!hasNext}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background-secondary px-3 py-1.5 text-sm text-foreground disabled:opacity-40 disabled:cursor-not-allowed hover:bg-background-tertiary focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background transition-colors"
            aria-label="Next page"
          >
            Next
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
