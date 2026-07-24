"""The ``probe`` subcommand — characterize good / bad / boundary ids.

Fetches a spread of sample ids (plus known-bad ones), parses each, and reports
the HTTP status, response size, parse status, and field count. The point is to
*learn the failure signature* — what a "not found" response actually looks like
(here: HTTP 200 + no details table + full site chrome) — before any walk, and to
confirm real offers parse into many fields with links captured.

Writes nothing to the database. Emits JSON-lines plus a final human report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config import Config
from .fetcher import OUTCOME_FETCHED, Fetcher
from .log import log
from .parser import STATUS_OK, parse_detail

# A spread across the id space + known-bad ids (0, far-future, gap).
DEFAULT_PROBE_IDS = [
    100,
    1000,
    10000,
    50000,
    100000,
    200000,
    300000,
    400000,
    0,
    88888888,
    99999999,
]


@dataclass
class ProbeRow:
    offer_id: int
    outcome: str
    http_status: int | None
    size_bytes: int
    parse_status: str
    field_count: int
    has_link: bool
    sample_labels: list[str]
    note: str


def _probe_one(fetcher: Fetcher, offer_id: int) -> ProbeRow:
    result = fetcher.fetch(offer_id)
    size = len(result.text or "")

    if result.outcome != OUTCOME_FETCHED:
        return ProbeRow(
            offer_id=offer_id,
            outcome=result.outcome,
            http_status=result.http_status,
            size_bytes=size,
            parse_status="-",
            field_count=0,
            has_link=False,
            sample_labels=[],
            note=result.error or result.outcome,
        )

    parsed = parse_detail(result.text or "")
    has_link = any(isinstance(v, dict) and "href" in v for v in parsed.fields.values())
    return ProbeRow(
        offer_id=offer_id,
        outcome=result.outcome,
        http_status=result.http_status,
        size_bytes=size,
        parse_status=parsed.status,
        field_count=parsed.field_count,
        has_link=has_link,
        sample_labels=parsed.labels[:4],
        note="ok" if parsed.status == STATUS_OK else parsed.status,
    )


def run_probe(config: Config, fetcher: Fetcher, ids: list[int]) -> list[ProbeRow]:
    fetcher.pin_language()
    rows: list[ProbeRow] = []
    for offer_id in ids:
        # honour the same politeness delay as the walk
        interval = config.min_request_interval()
        if rows and interval > 0:
            time.sleep(interval)
        row = _probe_one(fetcher, offer_id)
        rows.append(row)
        log(
            "probe",
            id=row.offer_id,
            outcome=row.outcome,
            http_status=row.http_status,
            size_bytes=row.size_bytes,
            parse_status=row.parse_status,
            fields=row.field_count,
            has_link=row.has_link,
        )

    _print_report(rows)
    return rows


def _print_report(rows: list[ProbeRow]) -> None:
    print("\n=== UZEX backfill probe report ===")
    header = f"{'id':>10} {'outcome':>14} {'http':>5} {'size':>8} {'parse':>12} {'fields':>7} {'link':>5}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r.offer_id:>10} {r.outcome:>14} {str(r.http_status):>5} "
            f"{r.size_bytes:>8} {r.parse_status:>12} {r.field_count:>7} "
            f"{('yes' if r.has_link else '-'):>5}"
        )

    ok_rows = [r for r in rows if r.parse_status == STATUS_OK]
    nf_rows = [r for r in rows if r.parse_status == "not_found"]
    print("\n-- learned signatures --")
    if ok_rows:
        sizes = [r.size_bytes for r in ok_rows]
        fields = [r.field_count for r in ok_rows]
        print(
            f"  OK offers:   HTTP 200, size ~{min(sizes)}-{max(sizes)}B, "
            f"{min(fields)}-{max(fields)} fields; details table present."
        )
        with_links = [r.offer_id for r in ok_rows if r.has_link]
        if with_links:
            print(f"               links captured as href objects on ids: {with_links}")
        print(f"               sample labels: {ok_rows[0].sample_labels}")
    if nf_rows:
        sizes = [r.size_bytes for r in nf_rows]
        print(
            f"  NOT_FOUND:   HTTP 200, size ~{min(sizes)}-{max(sizes)}B, "
            f"no details table (empty template) — treat as an id gap (skip)."
        )
    other = [r for r in rows if r.parse_status not in (STATUS_OK, "not_found", "-")]
    if other:
        print(f"  ANOMALIES:   {[(r.offer_id, r.parse_status) for r in other]}")
    unreached = [r for r in rows if r.outcome != OUTCOME_FETCHED]
    if unreached:
        print(f"  UNREACHED:   {[(r.offer_id, r.outcome) for r in unreached]}")
    print()
