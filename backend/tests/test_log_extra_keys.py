"""No `logger.x(..., extra={...})` may use a reserved `LogRecord` attribute name.

`logging.Logger.makeRecord` RAISES `KeyError: "Attempt to overwrite 'created' in
LogRecord"` when `extra` carries one of the names the record already owns. It does
not warn and it does not drop the key — the logging call itself becomes the
exception.

What makes this worth a test rather than a code review note is *when* it fires:
only once the logger is enabled for that level. Every instance this test was
written for sat at DEBUG or at INFO in a script nobody had configured logging for,
so all of them were invisible until something turned the level up:

- `seed_substances` used `extra={"created": …}` and crashed the moment the seeders
  were run through one entry point that calls `basicConfig` (09.09.2026). Until
  then each seeder ran as its own `python -m` with the root logger at WARNING.
- `storage_service.validate_upload` used `extra={"filename": …}` on all three of
  its branches — so raising the log level to diagnose a failing upload would have
  made every upload raise `KeyError` instead. The worst possible time.

`llm_clients.py` already carries a comment about this trap, so the codebase had
met it before and only fixed the one instance in front of it.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

#: Attributes `logging.LogRecord.__init__` sets. `makeRecord` refuses to overwrite
#: any of them. `message` and `asctime` are added by Formatter, and are refused too.
RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def _offenders() -> list[str]:
    found: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — nothing in app/ should fail to parse
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
                    continue
                for key in kw.value.keys:
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value in RESERVED
                    ):
                        rel = path.relative_to(_APP.parent)
                        found.append(f"{rel}:{key.lineno} — extra={{{key.value!r}: ...}}")
    return found


def test_no_reserved_logrecord_keys_in_extra() -> None:
    offenders = _offenders()
    assert not offenders, (
        "these logging calls pass a reserved LogRecord attribute in `extra=`, which "
        "makes logging.makeRecord raise KeyError as soon as the logger is enabled "
        "for that level — rename the key (e.g. `filename` → `file_name`):\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_can_actually_fail() -> None:
    """A scanner that silently matches nothing would pass forever."""
    import logging  # noqa: PLC0415

    logger = logging.getLogger("tests.reserved_key_probe")
    logger.setLevel(logging.INFO)
    with pytest.raises(KeyError, match="created"):
        logger.info("probe", extra={"created": 1})
