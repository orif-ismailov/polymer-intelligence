"""Contract-template authoring — the staff surface for `contract_templates`.

Until this module existed the table had exactly ONE writer, `seed_contract_templates`,
and no admin route at all. Two consequences, both of which we hit:

* A database whose seeders had not run had no templates and therefore no way to
  create a contract — the entire signing chain (draft → send → accept → both
  signatures → document → bundle) was dead, with no screen anywhere that said so.
* The bodies the seeder installs are DEV PLACEHOLDERS. `deploy/CLAUDE.md` has
  recorded since R3 that the production text plus legal sign-off is a launch
  blocker, and there was no mechanism to install that text short of a code change,
  a rebuild and a re-seed against a table the seeder refuses to overwrite.

## Validation is the reason this module is not just CRUD

`render.py` substitutes `{{ name }}` with `context.get(name, "")`. A name the
renderer cannot supply therefore becomes an EMPTY STRING — no exception, no log
line, no leftover `{{ }}` in the output to notice. The failure is a legally binding
document with a hole in it, discovered by whoever reads the PDF.

That is not hypothetical. The shipped `SAMPLE_LETTER_V1` body writes
`{{ buyer_legal_name }}` and `{{ seller_inn }}`, while the renderer produces
`initiator_*` and `counterparty_*` — so every commitment letter this platform has
ever generated names NEITHER PARTY: no company name, no INN, no address, no
director, on both sides. Eight placeholders, silently blank. `validate_body` is
what makes that a refused save instead.

## Versioning

One row per `code` (the column is UNIQUE), with `version` bumped on every body
change and the new body written to a NEW key — `store_contract_template` already
names them `contracts/templates/{code}_v{version}.html`. Old objects are never
deleted, so a contract that pinned `(template_id, template_version)` can still be
shown the exact bytes it was created from.

Editing cannot alter a signed contract: `Contract` freezes its rendered PDF in
`generated_document_path` + `document_sha256`, and the nightly
`verify_contract_integrity` compares against that PDF, not against the template.
Only DRAFT contracts re-render, which is why the list carries a usage count — an
operator editing a template should see how many are in flight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.contracts.models import Contract, ContractTemplate
from app.domains.contracts.render import _PLACEHOLDER, render_contract_html
from app.services import audit_service, storage_service

#: Mirrors `ck_contract_template_kind`. Kept here so a bad `kind` is a 422 from the
#: schema rather than an IntegrityError from Postgres.
KINDS: tuple[str, ...] = ("contract", "sample_letter")

#: Names `render_contract_html` injects for every render, whatever the template is.
_ALWAYS: frozenset[str] = frozenset({"contract_public_id", "generated_at"})

#: `contract_service._render_and_store` adds `title` to the variables it renders
#: with, so a contract body may use it even though no schema declares it.
_CONTRACT_EXTRA: frozenset[str] = frozenset({"title"})

#: An `<h2>` opening with its own ordinal — «1. Стороны», «2) Предмет», «1.2. Прочее».
#: The separator is required: without it «2026 год…» would lose its year.
_LEADING_ORDINAL = re.compile(r"^\s*\d+(?:\.\d+)*\s*[.)]\s+")
_H2 = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


class DuplicateCode(Exception):
    """A template with this `code` already exists (the column is UNIQUE)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TemplateBodyInvalid(Exception):
    """The body uses `{{ }}` names the renderer cannot fill."""

    def __init__(self, unknown: list[str]) -> None:
        super().__init__(", ".join(unknown))
        self.unknown = unknown


@dataclass
class BodyReport:
    """What `validate_body` found. `unknown` blocks a save; `warnings` do not."""

    used: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    unused_schema_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unknown


def _requisite_keys(kind: str) -> frozenset[str]:
    """The party fields the renderer will have, for this kind of document.

    Imported at call time from the two modules that BUILD those dicts, rather than
    restated here — a second copy is a copy that goes stale, and the whole point of
    the validator is that it knows what the renderer can actually supply.
    """
    if kind == "sample_letter":
        from app.domains.lab_orders.letters import REQUISITE_KEYS  # noqa: PLC0415

        return REQUISITE_KEYS
    from app.domains.contracts.service import REQUISITE_KEYS  # noqa: PLC0415

    return REQUISITE_KEYS


def renderable_names(kind: str, variables_schema: dict[str, object]) -> set[str]:
    """Every `{{ name }}` the renderer can fill for a template of this `kind`."""
    party = _requisite_keys(kind)
    names = set(_ALWAYS)
    if kind != "sample_letter":
        names |= _CONTRACT_EXTRA
    names |= {f"initiator_{k}" for k in party}
    names |= {f"counterparty_{k}" for k in party}
    properties = variables_schema.get("properties") or {}
    if isinstance(properties, dict):
        names |= set(properties)
    return names


def validate_body(body: str, kind: str, variables_schema: dict[str, object]) -> BodyReport:
    """Check a template body against what the renderer can actually supply."""
    allowed = renderable_names(kind, variables_schema)
    used = sorted(set(_PLACEHOLDER.findall(body)))
    unknown = sorted(set(used) - allowed)

    properties = variables_schema.get("properties") or {}
    declared = set(properties) if isinstance(properties, dict) else set()
    unused = sorted(declared - set(used))

    warnings: list[str] = []
    for raw in _H2.findall(body):
        title = _TAGS.sub("", raw).strip()
        if _LEADING_ORDINAL.match(title):
            # Didox prefixes its own `ordno` when it prints a «Договор НК», so a
            # title carrying one came out as «1. 1. Стороны» on the operator's form.
            warnings.append(
                f"section title «{title}» starts with its own number — Didox adds one "
                "when it prints, which reads as «1. 1. …»"
            )
    if unused:
        warnings.append(
            "declared in variables_schema but never used in the body: " + ", ".join(unused)
        )
    return BodyReport(used=used, unknown=unknown, unused_schema_keys=unused, warnings=warnings)


def preview(body: str, kind: str, variables_schema: dict[str, object]) -> str:
    """Render `body` with placeholder-shaped stand-ins, for the authoring screen.

    Every renderable name is filled with a visible token, so a hole in the output is
    a hole in the TEMPLATE rather than a gap in the sample data — which is the
    question an author is actually asking when they hit Preview.
    """
    names = renderable_names(kind, variables_schema)
    properties = variables_schema.get("properties") or {}
    titles = properties if isinstance(properties, dict) else {}

    def label(name: str) -> str:
        spec = titles.get(name)
        if isinstance(spec, dict) and spec.get("title"):
            return f"[{spec['title']}]"
        return f"[{name}]"

    party = _requisite_keys(kind)
    # Annotated `object` rather than inferred `str`: `dict` is invariant, and
    # `render_contract_html` takes `dict[str, object]` because a real party dict
    # carries whatever the requisites builder put in it.
    initiator: dict[str, object] = {k: f"[initiator_{k}]" for k in party}
    counterparty: dict[str, object] = {k: f"[counterparty_{k}]" for k in party}
    variables: dict[str, object] = {
        name: label(name)
        for name in names
        if not name.startswith(("initiator_", "counterparty_")) and name not in _ALWAYS
    }
    return render_contract_html(
        body,
        variables,
        initiator,
        counterparty,
        contract_public_id="[contract_public_id]",
        generated_at="[generated_at]",
    )


# ── Reads ─────────────────────────────────────────────────────────────────────


def usage_counts(db: Session) -> dict[int, int]:
    """`template_id → number of contracts referencing it`, for the list screen."""
    rows = db.execute(
        select(Contract.template_id, func.count(Contract.id)).group_by(Contract.template_id)
    ).all()
    return {int(template_id): int(count) for template_id, count in rows}


def list_templates(db: Session, *, include_inactive: bool = True) -> list[ContractTemplate]:
    stmt = select(ContractTemplate).order_by(ContractTemplate.code)
    if not include_inactive:
        stmt = stmt.where(ContractTemplate.is_active.is_(True))
    return list(db.execute(stmt).scalars().all())


def get_template(db: Session, template_id: int) -> ContractTemplate | None:
    return db.get(ContractTemplate, template_id)


def load_body(template: ContractTemplate) -> str:
    """The HTML behind `body_storage_path`. Separate from the row so the list
    screen does not fetch three objects from S3 to render a table."""
    return storage_service.get_object_text(template.body_storage_path)


# ── Writes ────────────────────────────────────────────────────────────────────


def create_template(
    db: Session,
    *,
    code: str,
    kind: str,
    name_ru: str,
    name_uz: str | None,
    name_en: str | None,
    body: str,
    variables_schema: dict[str, object],
    is_active: bool,
    staff_user_id: int,
) -> ContractTemplate:
    """Create a template at version 1. Raises before touching S3 if invalid."""
    report = validate_body(body, kind, variables_schema)
    if not report.ok:
        raise TemplateBodyInvalid(report.unknown)
    existing = db.execute(
        select(ContractTemplate).where(ContractTemplate.code == code)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateCode(code)

    path = storage_service.store_contract_template(code, 1, body)
    template = ContractTemplate(
        code=code,
        kind=kind,
        name_ru=name_ru,
        name_uz=name_uz,
        name_en=name_en,
        body_storage_path=path,
        variables_schema=variables_schema,
        version=1,
        is_active=is_active,
    )
    db.add(template)
    db.flush()
    audit_service.write_audit(
        db,
        staff_user_id,
        "contract_template.create",
        "contract_templates",
        str(template.id),
        {"code": code, "kind": kind, "version": 1},
    )
    return template


def update_template(
    db: Session,
    template: ContractTemplate,
    *,
    name_ru: str,
    name_uz: str | None,
    name_en: str | None,
    body: str | None,
    variables_schema: dict[str, object] | None,
    is_active: bool,
    staff_user_id: int,
) -> ContractTemplate:
    """Update metadata; bump the version and write a new object when the body changes.

    `code` and `kind` are NOT editable. `code` is what a contract's audit trail and
    every operator runbook names, and `kind` decides which renderer context the body
    was written against — changing either in place would silently redefine what
    existing rows mean. Make a new template instead.
    """
    schema = variables_schema if variables_schema is not None else dict(template.variables_schema)
    new_version = template.version
    if body is not None:
        report = validate_body(body, template.kind, schema)
        if not report.ok:
            raise TemplateBodyInvalid(report.unknown)
        current = load_body(template)
        if body != current:
            new_version = template.version + 1
            template.body_storage_path = storage_service.store_contract_template(
                template.code, new_version, body
            )
            template.version = new_version
    elif variables_schema is not None:
        # A schema change can strand a placeholder that used to resolve.
        report = validate_body(load_body(template), template.kind, schema)
        if not report.ok:
            raise TemplateBodyInvalid(report.unknown)

    template.name_ru = name_ru
    template.name_uz = name_uz
    template.name_en = name_en
    template.variables_schema = schema
    template.is_active = is_active
    db.flush()
    audit_service.write_audit(
        db,
        staff_user_id,
        "contract_template.update",
        "contract_templates",
        str(template.id),
        {"code": template.code, "version": new_version, "body_changed": body is not None},
    )
    return template


def set_active(
    db: Session, template: ContractTemplate, *, is_active: bool, staff_user_id: int
) -> ContractTemplate:
    """Show or hide a template in the cabinet's picker. Never deletes: contracts
    hold an FK to the row, and their history has to keep resolving."""
    template.is_active = is_active
    db.flush()
    audit_service.write_audit(
        db,
        staff_user_id,
        "contract_template.set_active",
        "contract_templates",
        str(template.id),
        {"code": template.code, "is_active": is_active},
    )
    return template
