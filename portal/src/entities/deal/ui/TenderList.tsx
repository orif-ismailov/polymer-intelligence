import type { ReactNode, Ref } from "react";

import { useTranslation } from "react-i18next";

import { cn, formatDate } from "@/shared/lib";
import { Badge, Card, ClockIcon } from "@/shared/ui";

import { tenderDeadline, type DeadlineTone } from "../lib/tenderDeadline";
import type { MarketRequest } from "../model/types";

/**
 * Buyer tenders as rows — one line per tender, scannable down a column.
 *
 * Shared by both tabs of «Открытые тендеры» (the tenders a supplier may answer,
 * and the quotes it has already given), which differ only in the fifth column,
 * the line under the product and the action. Two separate cards used to render
 * the same tender twice, slightly differently.
 *
 * Semantics: a list of tenders, each carrying a `<dl>` of its facts. The column
 * header is a visual aid only (`aria-hidden`); a screen reader hears
 * «Объём — 100 MT» from the row itself. On narrow screens the header is gone and
 * each row stacks, showing those same labels — so there is one markup for both
 * layouts, not a table plus a second set of mobile cards.
 */

/**
 * The columns, shared by the header and every row so they cannot drift.
 *
 * Every row is its own grid, so no track may size to its content — an `auto`
 * action column grew under a wider button («Моё предложение») and shifted that
 * one row's columns off the header. The action track is fixed; actions fill it.
 */
const GRID =
  "md:grid md:grid-cols-[minmax(0,2.4fr)_minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,0.9fr)_minmax(0,1.3fr)_12rem] md:items-center md:gap-x-5";

interface TenderListProps {
  /** Heading of the fifth column — «Приём ответов» or «Ваше предложение». */
  statusHeading: string;
  children: ReactNode;
}

export function TenderList({ statusHeading, children }: TenderListProps) {
  const { t } = useTranslation();
  return (
    <Card className="overflow-hidden p-0">
      <div
        aria-hidden="true"
        className={cn(
          "hidden border-b border-border bg-surface-2 px-5 py-2.5 text-xs font-medium uppercase tracking-wide text-text-subtle",
          GRID,
        )}
      >
        <span>{t("rfq.columns.product")}</span>
        <span>{t("rfq.columns.volume")}</span>
        <span>{t("rfq.columns.terms")}</span>
        <span>{t("rfq.columns.deliveryBy")}</span>
        <span>{statusHeading}</span>
        <span />
      </div>
      <ul role="list" className="divide-y divide-border">
        {children}
      </ul>
    </Card>
  );
}

interface TenderRowProps {
  request: MarketRequest;
  /** Label for the fifth fact on narrow screens; matches `statusHeading`. */
  statusLabel: string;
  status: ReactNode;
  /** Muted lines under the product — required documents, or the quote's terms. */
  detail?: ReactNode;
  action?: ReactNode;
  /** Expanded content under the row, full width (the quote form). */
  panel?: ReactNode;
  panelId?: string;
  highlighted?: boolean;
  rowRef?: Ref<HTMLLIElement>;
}

export function TenderRow({
  request,
  statusLabel,
  status,
  detail,
  action,
  panel,
  panelId,
  highlighted,
  rowRef,
}: TenderRowProps) {
  const { t } = useTranslation();
  const destination = [request.port_or_city, request.destination_country]
    .filter(Boolean)
    .join(", ");
  // A grade short enough to read as a code («PP», «H030 GP») is the chip the
  // marketplace cards carry; anything longer is a name. Either way it follows
  // the product, so product names line up down the column whatever the grade.
  const gradeChip = request.grade && request.grade.length <= 12 ? request.grade : null;
  const gradeText = request.grade && !gradeChip ? request.grade : null;

  return (
    <li
      ref={rowRef}
      className={cn(
        "px-4 py-4 transition-colors md:px-5",
        GRID,
        highlighted && "bg-brand-soft",
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className="font-semibold text-text">{request.product ?? "—"}</p>
          {gradeChip ? (
            <Badge tone="brand" className="rounded-md">
              {gradeChip}
            </Badge>
          ) : null}
          {gradeText ? <span className="text-sm text-text-muted">{gradeText}</span> : null}
          {request.urgency === "high" ? <Badge tone="danger">{t("rfq.urgent")}</Badge> : null}
        </div>
        {detail}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 md:contents">
        <Fact label={t("rfq.columns.volume")}>
          <span className="num font-semibold text-text">
            {request.volume} {request.volume_unit}
          </span>
        </Fact>
        <Fact label={t("rfq.columns.terms")}>
          <span className="font-medium text-text">{request.incoterms}</span>
          {destination ? <span className="text-text-muted"> · {destination}</span> : null}
        </Fact>
        <Fact label={t("rfq.columns.deliveryBy")}>
          <span className="num text-text">
            {request.desired_date ? formatDate(request.desired_date) : "—"}
          </span>
        </Fact>
        <Fact label={statusLabel}>{status}</Fact>
      </dl>

      {action ? <div className="mt-4 md:mt-0 md:justify-self-end">{action}</div> : null}

      {panel ? (
        <div id={panelId} className="mt-4 border-t border-border pt-4 md:col-span-full">
          {panel}
        </div>
      ) : null}
    </li>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-subtle md:sr-only">{label}</dt>
      <dd className="mt-0.5 text-sm md:mt-0">{children}</dd>
    </div>
  );
}

const DEADLINE_TONE: Record<DeadlineTone, "neutral" | "warning" | "danger"> = {
  neutral: "neutral",
  warning: "warning",
  lastDay: "danger",
  closed: "neutral",
  unknown: "neutral",
};

/**
 * Time left to quote. Colour is never the only signal — the words change with it
 * («ещё 5 дн.» → «меньше суток» → «приём закрыт»).
 */
export function TenderDeadlineBadge({ request }: { request: MarketRequest }) {
  const { t } = useTranslation();
  const deadline = tenderDeadline(request.created_at, request.validity_days);
  if (deadline.tone === "unknown") return <span className="text-text-muted">—</span>;

  const label =
    deadline.tone === "closed"
      ? t("rfq.deadline.closed")
      : deadline.tone === "lastDay"
        ? t("rfq.deadline.lastDay")
        : t("rfq.deadline.daysLeft", { count: deadline.daysLeft });

  return (
    <Badge tone={DEADLINE_TONE[deadline.tone]} icon={<ClockIcon size={12} />}>
      <span className="num">{label}</span>
    </Badge>
  );
}
