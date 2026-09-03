"""What the daily/evening report cost.

The digest is the single most expensive LLM call this platform makes — the v6
payload runs ~6.5k Cyrillic-dense output tokens and it fires twice a day — and it
was the only LLM caller journalling no token count anywhere at all. Signal
extraction and news classification write `parse_runs`, the substance hint writes
`substance_suggestions`, buyer-request analysis at least had a JSONB block to put
them in. The report had nowhere, so `/admin/llm-spend` and the analytics page
could not see the biggest line item.

NULL vs 0 is load-bearing here and the reason these are nullable:

  NULL  no LLM call was attempted (`generate_report(use_llm=False)`, which is the
        path every test takes and the path a deployment with the news AI switched
        off takes forever).
  0     a call was attempted and the provider reported no usage.

Collapsing the two to 0 would make "the AI is off" and "the AI answered nothing"
indistinguishable, and the second is a fault worth seeing.

Tokens are recorded even when the digest FAILED and the report degraded to the
rule-based summary. A call that returned unparseable JSON was billed exactly like
one that worked, and a failure costing 6.5k tokens is precisely the one an
operator needs on the page — `generated_by` already distinguishes the two
outcomes ('rule_based' vs the model id).

Backfill is impossible on purpose: existing rows predate the measurement and stay
NULL rather than being given an invented number.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("tokens_in", sa.Integer(), nullable=True))
    op.add_column("reports", sa.Column("tokens_out", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Drop the cost columns. The reports themselves are untouched."""
    op.drop_column("reports", "tokens_out")
    op.drop_column("reports", "tokens_in")
