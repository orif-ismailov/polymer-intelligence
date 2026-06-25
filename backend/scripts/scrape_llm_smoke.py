"""
One-shot local smoke: live-scrape UZEX, then run the real Phase-5 LLM extractor
(parsing.extractor.extract_signal) on the scraped rows.

This is a MANUAL end-to-end check, not part of the product pipeline. The real
ingest pipeline routes structured UZEX rows through a rule-based signal builder;
this script deliberately feeds the scraped rows to the LLM so you can watch the
scraper AND the Anthropic key work together end-to-end.

Run it INSIDE the api container so it uses the container's ANTHROPIC_API_KEY and
the same network egress the scheduled jobs use:

    docker compose -f deploy/docker-compose.dev.yml exec api \
        python -m scripts.scrape_llm_smoke --rows 3

Flags:
    --rows N    how many scraped rows to push through the LLM (default 3)
    --no-llm    scrape only; never construct the Anthropic client
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from types import SimpleNamespace


def _looks_like_real_key() -> bool:
    """True only for a real-looking key, so a placeholder never bills a request."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key.startswith("sk-ant-") and "test" not in key and len(key) > 30


async def _scrape() -> list:
    """Live-scrape the UZEX offers pages via the real adapter (no DB needed).

    fetch() only reads source.config, so a SimpleNamespace stand-in avoids
    needing a persisted Source row. We pass the FULL default config (urls +
    table_selector + column mapping) — an empty config would fall back to the
    default URLs but leave parse_table_rows without a selector/columns, yielding
    zero rows. This mirrors the config the seeded source row carries.
    """
    from app.ingest.uzex.adapters import UzexOffersAdapter, UzexOffersConfig

    adapter = UzexOffersAdapter()
    source = SimpleNamespace(id=0, config=UzexOffersConfig().model_dump())
    return await adapter.fetch(source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="UZEX live scrape + Phase-5 LLM extraction smoke"
    )
    parser.add_argument(
        "--rows", type=int, default=3,
        help="How many scraped rows to run through the LLM (default 3)",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Scrape only; skip the LLM calls",
    )
    args = parser.parse_args(argv)

    print("== UZEX live scrape (uzex_offers) ==", flush=True)
    drafts = asyncio.run(_scrape())
    print(f"Scraped {len(drafts)} rows from uzex.uz\n", flush=True)
    for d in drafts[:5]:
        content = (d.content or "")[:160]
        print(f"  [{d.external_id}] {content}")

    if not drafts:
        print(
            "\nNo rows scraped — the live page may be empty (UZEX trades on "
            "weekday business hours, Asia/Tashkent) or the table selector is stale."
        )
        return 1

    if args.no_llm:
        return 0

    if not _looks_like_real_key():
        klen = len(os.environ.get("ANTHROPIC_API_KEY", ""))
        print(
            f"\n!! ANTHROPIC_API_KEY is missing or a placeholder in this container "
            f"(length={klen}) — skipping the LLM step."
        )
        return 2

    # Imported here so a scrape-only / no-key run never constructs the client.
    from instructor.core import InstructorRetryException

    from parsing.extractor import extract_signal
    from parsing.schemas import BudgetExceeded
    from parsing.text_prep import prepare_message_text

    n = args.rows
    print(f"\n== LLM extraction (extract_signal) on first {n} scraped rows ==", flush=True)
    for i, d in enumerate(drafts[:n], 1):
        text = prepare_message_text(d.content or "")
        if not text:
            print(f"\n[{i}] blank content — skipped (G6 cost guard)")
            continue
        print(f"\n[{i}] input: {text[:200]}", flush=True)
        try:
            result, journal = extract_signal(text)
        except BudgetExceeded:
            print("    BudgetExceeded — daily token budget hit; pipeline would fall back to rule-based.")
            break
        except InstructorRetryException as exc:
            print(f"    InstructorRetryException — schema validation failed after retries: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — smoke tool: surface any failure verbatim
            print(f"    ERROR: {type(exc).__name__}: {exc}")
            continue
        print(
            f"    relevant={result.is_relevant} kind={result.kind} "
            f"product={result.product} grade={result.grade_text} "
            f"vol={result.volume} price={result.price} cur={result.currency} "
            f"cp={result.counterparty_text} conf={result.confidence}"
        )
        print(
            f"    tokens_in={journal['tokens_in']} tokens_out={journal['tokens_out']} "
            f"cache_read={journal['cache_read_tokens']} "
            f"latency_ms={journal['latency_ms']:.0f} model={journal['model']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
