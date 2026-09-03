#!/usr/bin/env python
"""
Move panel-managed settings out of `.env` and into the admin panel.

The switches are edited at `/admin/settings` now, but a deployment that has been
running for a while still carries them in its `.env` — and most of those lines
are not restating the default, they are carrying a real decision. On this repo's
own dev file, ten of them did: the dangerous-substance publish gate was ON, the
gov registry was pointed at Didox, the news AI was OFF. Deleting those lines
would silently revert every one of them on the next boot.

So this migrates rather than deletes. For each panel-managed key present in
`.env`, it writes the CURRENT value as an `app_settings` override and then drops
the line. The effective value is unchanged — `get()` resolves override first,
`.env` second — and the setting ends up where the panel says it lives, shown as
the deliberate exception it always was.

Two things it will not touch:

  * A value equal to the shipped default. That line was saying nothing, so it is
    dropped without writing a row; an override recording "same as default" is
    noise the panel would render as an exception.
  * `ANTHROPIC_API_KEY`. It is required at startup and `Settings` validates
    before anything reads a database, so it has no override to fall back to. It
    stays in `.env` and this refuses to move it.

Secrets that DO move are Fernet-encrypted by `set_override`, which is a small
improvement on plaintext in a file.

    python scripts/import_env_overrides.py            # show what would move
    python scripts/import_env_overrides.py --apply    # write rows, rewrite .env
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

sys.path.insert(0, str(REPO_ROOT / "backend"))

_ASSIGNMENT = re.compile(r"^([A-Z0-9_]+)=(.*)$")
_COMMENT = re.compile(r"\s+#\s?(.*)$")

#: Required at startup, so it cannot live only in a database the app has not
#: connected to yet. See the module docstring.
_IMMOVABLE = frozenset({"ANTHROPIC_API_KEY"})


def _env_lines() -> list[str]:
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _parse(lines: list[str]) -> dict[str, str]:
    out = {}
    for line in lines:
        m = _ASSIGNMENT.match(line)
        if m:
            value = m.group(2)
            comment = _COMMENT.search(value)
            out[m.group(1)] = (value[: comment.start()] if comment else value).strip()
    return out


def plan() -> tuple[list[tuple[str, str, str]], list[str], list[str]]:
    """`(to_migrate, redundant, immovable)` — what happens to each key."""
    from app.core.config import Settings  # noqa: PLC0415
    from app.services.settings_service import SPECS  # noqa: PLC0415

    present = _parse(_env_lines())
    migrate, redundant, immovable = [], [], []
    for spec in SPECS.values():
        if not spec.overridable or spec.env_var not in present:
            continue
        if spec.env_var in _IMMOVABLE:
            immovable.append(spec.env_var)
            continue
        raw = present[spec.env_var]
        field = Settings.model_fields[spec.env_var]
        default = "" if field.default is None else field.default
        shown = "true" if default is True else "false" if default is False else str(default)
        if raw == shown:
            redundant.append(spec.env_var)   # says nothing; drop without a row
        else:
            migrate.append((spec.key, spec.env_var, raw))
    return migrate, redundant, immovable


def run(*, apply: bool) -> int:
    migrate, redundant, immovable = plan()

    for _key, env_var, raw in migrate:
        print(f"  move  {env_var:34} -> app_settings override")
    for env_var in redundant:
        print(f"  drop  {env_var:34} (equal to the default; says nothing)")
    for env_var in immovable:
        print(f"  keep  {env_var:34} (required at startup; no override can precede it)")

    if not apply:
        print(f"\n{len(migrate)} to move, {len(redundant)} to drop — re-run with --apply")
        return 0

    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.services import settings_service  # noqa: PLC0415

    with SessionLocal() as db:
        for key, env_var, raw in migrate:
            settings_service.set_override(db, key, raw, None)
            print(f"  wrote override {key} = {'<secret>' if 'PASSWORD' in env_var or 'TOKEN' in env_var else raw!r}")
        db.commit()
    # Every other process is holding a snapshot; without this they keep reading
    # `.env` values that are about to disappear from the file.
    settings_service.bump_generation()

    drop = {env_var for _k, env_var, _v in migrate} | set(redundant)
    kept = []
    for line in _env_lines():
        m = _ASSIGNMENT.match(line)
        if m and m.group(1) in drop:
            continue
        kept.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip("\n") + "\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"\nremoved {len(drop)} lines from .env")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the rows and rewrite .env")
    raise SystemExit(run(apply=parser.parse_args().apply))
