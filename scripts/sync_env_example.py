#!/usr/bin/env python
"""
Keep `deploy/.env.example` in step with `Settings` — the mechanical parts only.

The contract file is written by hand and that is deliberate: most of its value is
the prose. Why `DIDOX_BASE_URL` points at the test contour, why the dangerous-
substance gate ships off, what the connection-count arithmetic multiplies out to
— none of that can be derived from a pydantic field, and a generator that
replaced it with `# int, 5..1440` would trade the useful half of the file for
tidiness.

Two things CAN be derived, and both rot silently by hand:

**`[panel: X]` markers.** Which settings are editable at `/admin/settings/X` is
`SettingSpec.group`, and it changes whenever a spec is added, regrouped or made
env-only. A marker nobody updated is worse than no marker: it sends an operator
to a page where the setting is not.

**Presence.** A `Settings` field with no line here is a setting nobody knows
exists — `test_env_contract_sync` already fails on it, but failing tells you to
go and write the line by hand in the right section. This appends a stub with the
real default so the remaining work is one sentence of prose.

VALUES ARE NEVER REWRITTEN, and that is not laziness. Two documented values
deliberately differ from the code default: `S3_ENDPOINT` shows the compose
address where the field defaults to empty, and `CORS_ALLOWED_ORIGINS` shows the
comma-separated env form that a `mode="before"` validator splits into the list
the field actually holds. Forcing value == default would corrupt both. What the
test does instead is check every documented value is one `Settings` would ACCEPT,
which catches a broken example without pretending the file is a mirror.

    python scripts/sync_env_example.py           # fix in place
    python scripts/sync_env_example.py --check   # report only; non-zero if stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"

sys.path.insert(0, str(REPO_ROOT / "backend"))

#: `KEY=value` at the start of a line. Commented-out optional keys are left alone:
#: they are documentation of a variable a deployment may not set at all.
_ASSIGNMENT = re.compile(r"^([A-Z0-9_]+)=(.*)$")
#: A comment introduced by WHITESPACE. That is the dotenv rule: without a space
#: before it, `#` is part of the value. Honouring it is not pedantry — the first
#: run of this tool found `INGEST_USER_AGENT=…example)# [panel: ingest]`, where a
#: hand-added marker had been glued straight onto a value longer than the pad
#: column and had silently become part of the user agent string.
_COMMENT = re.compile(r"\s+#\s?(.*)$")
_MARKER = re.compile(r"\[panel:\s*[a-z_]+\]\s*")
#: The same marker glued to a value with no separating space — the damage above.
#: Stripped before parsing so a repair is possible rather than compounding.
_GLUED_MARKER = re.compile(r"(?<!\s)#\s*\[panel:\s*[a-z_]+\]\s*")

#: Where the value column ends. A longer value simply gets one space, never zero
#: — that is the bug above, and `ljust` alone reintroduces it.
_PAD = 43


#: The single panel-managed setting the contract still lists.
#:
#: It is REQUIRED and `Settings` validates at import — before anything has
#: connected to the database an override would live in — so unlike every other
#: overridable spec it cannot live only in the panel. A deployment that copied
#: the file without it would fail to boot, with nothing in the file to say why.
DOCUMENTED_PANEL_KEY = "ANTHROPIC_API_KEY"


def _panel_groups() -> dict[str, str]:
    """The panel-managed keys still listed here — exactly one, and it gets a marker."""
    from app.services.settings_service import SPECS  # noqa: PLC0415

    return {
        spec.env_var: spec.group
        for spec in SPECS.values()
        if spec.overridable and spec.env_var == DOCUMENTED_PANEL_KEY
    }


def _must_be_absent() -> dict[str, str]:
    """Everything else panel-managed, which the contract deliberately omits.

    Defaults are on `Settings`; values are edited at `/admin/settings`, and the
    credentials among them are stored Fernet-encrypted rather than in plaintext
    here. Re-adding one would put a second copy of a default in a file that is not
    its source — the drift this repo already paid for when `.env` and
    `backend/.env` disagreed on ten keys.
    """
    from app.services.settings_service import SPECS  # noqa: PLC0415

    return {
        spec.env_var: spec.group
        for spec in SPECS.values()
        if spec.overridable and spec.env_var != DOCUMENTED_PANEL_KEY
    }


def _render_default(name: str) -> str:
    from app.core.config import Settings  # noqa: PLC0415

    field = Settings.model_fields[name]
    if field.is_required():
        return ""
    default = field.default
    if default is None:
        return ""
    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, (list, tuple)):
        return ",".join(str(v) for v in default)
    return str(default)


def _rewrite(line: str, group: str | None) -> str:
    """Put `[panel: group]` on this assignment, or take a stale one off.

    Returns the line UNCHANGED when the marker is already right. A sync tool that
    also reflows padding produces a diff nobody reads, and the one thing it must
    never do is bury a real change among forty cosmetic ones.
    """
    match = _ASSIGNMENT.match(line)
    if match is None:
        return line
    key, rest = match.group(1), match.group(2)

    repaired = _GLUED_MARKER.sub("", rest)
    comment_match = _COMMENT.search(repaired)
    value = repaired[: comment_match.start()] if comment_match else repaired
    comment = comment_match.group(1) if comment_match else ""
    comment = _MARKER.sub("", comment).strip()

    if group:
        comment = f"[panel: {group}] {comment}".strip()

    value = value.rstrip()
    if not comment:
        rebuilt = f"{key}={value}"
    else:
        stem = f"{key}={value}"
        rebuilt = stem.ljust(max(_PAD, len(stem) + 1)) + f"# {comment}"

    # Only report a change when the MARKER differs; otherwise keep the original
    # bytes, whatever its spacing happens to be.
    def markers(text: str) -> list[str]:
        return _MARKER.findall(text) + _GLUED_MARKER.findall(text)

    if markers(line) == markers(rebuilt) and _GLUED_MARKER.search(line) is None:
        return line
    return rebuilt


def sync(*, check: bool, path: Path | None = None) -> int:
    """Returns 0 when in sync, 1 when stale. `path` is for tests: a guard nobody
    can see fail is a guard nobody should trust."""
    from app.core.config import Settings  # noqa: PLC0415

    target = path or ENV_EXAMPLE
    groups = _panel_groups()
    absent = _must_be_absent()
    original = target.read_text(encoding="utf-8").splitlines()

    # A panel-managed switch that reappeared as an assignment is removed: the file
    # is not where its default lives any more, and a second copy is drift waiting.
    reintroduced = [
        m.group(1) for line in original
        if (m := _ASSIGNMENT.match(line)) and m.group(1) in absent
    ]
    out = [
        _rewrite(line, groups.get(m.group(1))) if (m := _ASSIGNMENT.match(line)) else line
        for line in original
        if not ((m2 := _ASSIGNMENT.match(line)) and m2.group(1) in absent)
    ]

    documented = {m.group(1) for line in out if (m := _ASSIGNMENT.match(line))}
    # Commented-out keys count as documented — they are a deliberate "you may set
    # this", and `test_env_contract_sync` reads them the same way.
    documented |= {
        m.group(1) for line in out if (m := re.match(r"^#\s*([A-Z0-9_]+)=", line))
    }
    # A field with no line here is undocumented — UNLESS it is one of the switches
    # the panel owns, which are absent on purpose.
    missing = [n for n in Settings.model_fields if n not in documented and n not in absent]

    if missing:
        out += [
            "",
            "# ── NEEDS DOCUMENTATION ───────────────────────────────────────────────────────",
            "# Appended by scripts/sync_env_example.py because these fields exist on",
            "# `Settings` and nothing here described them. The value is the code default;",
            "# replace this block with a real section and a sentence saying what each does.",
        ]
        for name in missing:
            out.append(_rewrite(f"{name}={_render_default(name)}", groups.get(name)))

    # Exactly one trailing newline. Removing the last assignment in a file
    # otherwise leaves the blank line that separated it, and the next run has
    # nothing to say about it — a diff that appears once and never resolves.
    while out and not out[-1].strip():
        out.pop()

    changed = out != original
    if not changed:
        print("deploy/.env.example is in sync")
        return 0

    diff = [
        (i + 1, before, after)
        for i, (before, after) in enumerate(zip(original, out, strict=False))
        if before != after
    ]
    for lineno, before, after in diff:
        print(f"  {lineno:4} - {before}\n       + {after}")
    for name in missing:
        print(f"  ---- + {name} (undocumented; appended)")
    for name in reintroduced:
        print(f"  ---- - {name} (panel-managed; removed — it is edited at /admin/settings)")

    if check:
        print(f"\n{len(diff) + len(missing) + len(reintroduced)} line(s) stale — run: make env-sync")
        return 1

    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nupdated {len(diff) + len(missing) + len(reintroduced)} line(s)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only; non-zero if stale")
    raise SystemExit(sync(check=parser.parse_args().check))
