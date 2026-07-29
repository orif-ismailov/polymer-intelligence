"""Inspect the optimistic-claim UPDATE a service issued against a mock Session.

Moderation decisions no longer mutate the ORM object and flush — they issue a
guarded ``UPDATE ... WHERE status = <expected>`` so two concurrent deciders
cannot each land half a verdict (QA #1). Against a MagicMock session there is no
row to read back, so the assertion moves to the statement itself: this helper
pulls it out of ``db.execute`` and hands back the SET values plus the WHERE
binds, which is where the guard actually lives.

Not a pytest module (leading underscore).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Update


def claim_update(db: Any, table: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (set_values, where_binds) of the UPDATE issued against `table`.

    Raises AssertionError when no such statement was executed — "the service
    silently did nothing" must fail loudly, not pass vacuously.
    """
    for call in db.execute.call_args_list:
        stmt = call.args[0] if call.args else None
        if isinstance(stmt, Update) and stmt.table.name == table:
            compiled = stmt.compile()
            params = dict(compiled.params)
            set_keys = {c.name for c in stmt.table.columns} & set(params)
            where = {k: v for k, v in params.items() if k not in set_keys}
            return {k: params[k] for k in set_keys}, where
    raise AssertionError(f"no UPDATE against {table} was executed")
