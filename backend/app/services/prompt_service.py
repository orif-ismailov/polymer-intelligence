"""
Authoring LLM prompt versions from the admin panel.

An operator edits the news prompt and saves; that writes a NEW version. It never
rewrites an old one, and the reason is worth stating because the alternative
looks harmless: `parsing.news_extractor` caches the loaded prompt per process,
keyed on the version string alone. A mutable body would leave workers that had
already loaded `v3` running the old text while restarted ones ran the new — and
every `parse_runs` row from both would say `prompt_version="v3"`, so afterwards
nothing could say which article got which prompt. That ambiguity cannot be
repaired later, which is why the table is append-only and this module has no
update path.

Two files are the source of a version's text, in this order:

    the `prompt_versions` row, if one exists, else the shipped
    `parsing/prompts/<family>_<version>.md`

— the same layering as `settings_service`, and for the same reason: a deployment
that never opens the panel runs exactly what shipped, and an authored version is
visibly an authored version rather than a mystery default.

Which version is LIVE is not decided here. That is the `news_prompt_version`
setting, so activating one is an ordinary override and inherits its validation,
its audit row, the Redis generation bump and the cross-process propagation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.paths import PROMPTS_DIR
from app.models.prompts import FAMILIES, FAMILY_NEWS_EXTRACT, PromptVersion
from app.models.staff import StaffUser
from app.services import audit_service

#: An upper bound on an authored prompt, in characters.
#:
#: Not a technical limit — the model would accept far more — but a prompt is
#: BILLED on every article, so length is a recurring cost an operator cannot see
#: at the moment they paste. The shipped `news_extract_v3.md` is ~4.4 KB; this
#: leaves room for several times that and still refuses a pasted document.
MAX_BODY_CHARS = 64_000

_VERSION_RE = re.compile(r"^v(\d+)$")


class InvalidPrompt(Exception):
    """A prompt was refused. The message is safe to show an operator."""


@dataclass(frozen=True)
class PromptVersionInfo:
    """One version, from either source, as the panel needs to render it."""

    version: str
    #: True → this text came out of the image, and there is no row for it.
    shipped: bool
    #: None for shipped versions; nobody authored them.
    created_by: str | None
    created_at: object | None
    note: str | None
    size: int


def _assert_family(family: str) -> None:
    if family not in FAMILIES:
        raise InvalidPrompt(f"Unknown prompt family: {family}")


def body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ── Reading ───────────────────────────────────────────────────────────────────


def shipped_versions(family: str) -> dict[str, str]:
    """The `<family>_v*.md` files baked into this image, version → body.

    Globbed rather than listed for the reason `settings_service` globs the same
    directory: the hazard is a version that is NAMED somewhere and absent from
    disk, and the only way to be sure is to look.
    """
    _assert_family(family)
    found: dict[str, str] = {}
    for path in PROMPTS_DIR.glob(f"{family}_v*.md"):
        version = path.stem.removeprefix(f"{family}_")
        if _VERSION_RE.match(version):
            found[version] = path.read_text(encoding="utf-8")
    return found


def stored_bodies(db: Session, family: str | None = None) -> dict[tuple[str, str], str]:
    """Every authored body as `{(family, version): body}`.

    Loaded wholesale because `settings_service` carries this into each process's
    snapshot on refresh, and a prompt the loader cannot find in memory is a
    database read on a path that must not make one.
    """
    stmt = select(PromptVersion)
    if family is not None:
        stmt = stmt.where(PromptVersion.family == family)
    return {(row.family, row.version): row.body for row in db.execute(stmt).scalars()}


def list_versions(db: Session, family: str) -> list[PromptVersionInfo]:
    """Every version of a family, shipped and authored, newest first.

    Authored rows win over a shipped file of the same name. That collision should
    not happen — `next_version` counts both sources — but if a release ever ships
    a file whose name an operator already used, the row is the one `parse_runs`
    has been journalling, and silently swapping it for the file would rewrite
    history.
    """
    _assert_family(family)
    rows = (
        db.execute(
            select(PromptVersion, StaffUser.full_name)
            .outerjoin(StaffUser, StaffUser.id == PromptVersion.created_by)
            .where(PromptVersion.family == family)
            .order_by(PromptVersion.id.desc())
        )
        .all()
    )

    infos: list[PromptVersionInfo] = [
        PromptVersionInfo(
            version=row.PromptVersion.version,
            shipped=False,
            created_by=row.full_name,
            created_at=row.PromptVersion.created_at,
            note=row.PromptVersion.note,
            size=len(row.PromptVersion.body),
        )
        for row in rows
    ]
    authored = {info.version for info in infos}

    for version, body in shipped_versions(family).items():
        if version not in authored:
            infos.append(
                PromptVersionInfo(
                    version=version,
                    shipped=True,
                    created_by=None,
                    created_at=None,
                    note=None,
                    size=len(body),
                )
            )

    infos.sort(key=lambda i: _version_number(i.version), reverse=True)
    return infos


def resolve_body(db: Session, family: str, version: str) -> str | None:
    """The text of one version, authored first then shipped, or None.

    Only for the admin surface, which has a session. The extraction path reads
    the in-memory snapshot instead — see `settings_service.prompt_body`.
    """
    _assert_family(family)
    row = db.execute(
        select(PromptVersion).where(
            PromptVersion.family == family, PromptVersion.version == version
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.body
    return shipped_versions(family).get(version)


def _version_number(version: str) -> int:
    match = _VERSION_RE.match(version)
    return int(match.group(1)) if match else 0


def next_version(db: Session, family: str) -> str:
    """The name the next authored version will get.

    Counts BOTH sources. Numbering only against the table would hand out `v4` to
    an operator on an image that already ships one, and the collision would land
    on the unique constraint as a 500 rather than as anything anyone could act on.
    """
    _assert_family(family)
    stored = {
        row.version for row in db.execute(
            select(PromptVersion).where(PromptVersion.family == family)
        ).scalars()
    }
    highest = max(
        (_version_number(v) for v in stored | set(shipped_versions(family))),
        default=0,
    )
    return f"v{highest + 1}"


# ── Writing ───────────────────────────────────────────────────────────────────


def create_version(
    db: Session,
    family: str,
    body: str,
    *,
    note: str | None = None,
    staff_user_id: int | None = None,
) -> tuple[PromptVersion, bool]:
    """Author a new version. Returns `(row, created)`; does NOT commit.

    `created=False` means the text already exists under another version and that
    one is returned instead. An operator who presses Save twice, or who reverts
    their edit before saving, gets the version they already have rather than a
    stack of identical ones — the `raw_items` content-hash bargain, where a
    repeat is a no-op rather than a duplicate.

    Flushes without committing so the version row and its audit row land in one
    transaction, matching `registry.record_snapshot` and `audit_service`'s own
    contract.
    """
    _assert_family(family)
    body = _validated(body)
    digest = body_sha256(body)

    existing = db.execute(
        select(PromptVersion).where(
            PromptVersion.family == family, PromptVersion.body_sha256 == digest
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    version = next_version(db, family)
    row = PromptVersion(
        family=family,
        version=version,
        body=body,
        body_sha256=digest,
        note=(note or "").strip() or None,
        created_by=staff_user_id,
    )
    db.add(row)
    db.flush()

    audit_service.write_audit(
        db,
        staff_user_id,
        "prompt.version_created",
        "prompt_versions",
        str(row.id),
        # The version, its size and its hash — never the text. `audit_log` has a
        # different retention story from this table, and the body is already
        # stored, immutably, one row away.
        {"family": family, "version": version, "bytes": len(body), "sha256": digest},
    )
    return row, True


def _validated(body: str) -> str:
    """Refuse a body that would break the classifier quietly.

    An empty prompt is a VALID system prompt: the model runs with no instructions
    and classifies everything badly, which is exactly the failure that hid behind
    `load_news_prompt`'s old `return ""`. It is refused here, in the schema, and
    at the API — three times, because it produces no error anywhere downstream.
    """
    if not body or not body.strip():
        raise InvalidPrompt("The prompt cannot be empty.")
    if len(body) > MAX_BODY_CHARS:
        raise InvalidPrompt(
            f"The prompt is {len(body)} characters; the limit is {MAX_BODY_CHARS}. "
            "It is billed on every article, so length is a recurring cost."
        )
    return body


__all__ = [
    "FAMILY_NEWS_EXTRACT",
    "MAX_BODY_CHARS",
    "InvalidPrompt",
    "PromptVersionInfo",
    "body_sha256",
    "create_version",
    "list_versions",
    "next_version",
    "resolve_body",
    "shipped_versions",
    "stored_bodies",
]
