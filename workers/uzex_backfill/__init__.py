"""UZEX offer-detail archive backfill worker.

A self-contained crawler that walks the uzex.uz offer-detail ID space, fetches
each server-rendered detail page, parses it generically into ``{label: value}``
pairs, and stores each offer as JSON in PostgreSQL.

Deliberately standalone: it imports NOTHING from the main application code, owns
its DB tables (additive-only), and runs as its own process — never inside the
app's Celery. The main project can be redeployed at any time with zero effect on
a running walk, and vice versa.

Entry point: ``python -m uzex_backfill <subcommand>``.
"""

__version__ = "1.0.0"
