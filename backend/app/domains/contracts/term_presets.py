"""A company's saved contract terms — «шаблоны условий».

Each company has its own payment and delivery terms, and they used to be typed
again into every contract. A preset saves them once; choosing it on the contract
form fills those fields, and the contract keeps its own copy in `variables`.

Only TERMS are kept. The legal text stays the platform's template, reviewed once
for everyone, and price, quantity and product belong to each deal. Enum values
are checked against the active contract templates, so a preset can never fill a
form with a value the template would refuse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.core.time import utcnow
from app.domains.contracts.models import ContractTemplate, ContractTermPreset

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.domains.accounts.models import UserAccount

#: The variables a preset may carry — the terms, never the deal's own numbers.
PRESET_KEYS: frozenset[str] = frozenset(
    {"currency", "unit", "incoterms", "payment_terms", "delivery_window", "special_conditions"}
)

_MAX_VALUE = 4000


class InvalidTerms(Exception):
    def __init__(self, fields: list[str]) -> None:
        super().__init__(", ".join(fields))
        self.fields = fields


class PresetNameTaken(Exception):
    """Another live preset of this company already has the name."""


class PresetNotFound(Exception):
    """No live preset with this id belongs to the company."""


def _allowed_values(db: Session) -> dict[str, set[str]]:
    """`key → allowed values` from every active contract template's schema."""
    allowed: dict[str, set[str]] = {}
    templates = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.is_active.is_(True), ContractTemplate.kind == "contract")
        .all()
    )
    for template in templates:
        schema = template.variables_schema if isinstance(template.variables_schema, dict) else {}
        props = schema.get("properties")
        if not isinstance(props, dict):
            continue
        for key, spec in props.items():
            if isinstance(spec, dict) and isinstance(spec.get("enum"), list):
                allowed.setdefault(key, set()).update(str(v) for v in spec["enum"])
    return allowed


def clean_terms(db: Session, terms: dict[str, object]) -> dict[str, str]:
    """Blank values dropped, everything else a known key with an allowed value."""
    allowed = _allowed_values(db)
    cleaned: dict[str, str] = {}
    errors: set[str] = set()
    for key, raw in terms.items():
        if key not in PRESET_KEYS or not isinstance(raw, str) or len(raw) > _MAX_VALUE:
            errors.add(key)
            continue
        value = raw.strip()
        if not value:
            continue
        if key in allowed and value not in allowed[key]:
            errors.add(key)
            continue
        cleaned[key] = value
    if errors:
        raise InvalidTerms(sorted(errors))
    return cleaned


def list_presets(db: Session, company_id: int) -> list[ContractTermPreset]:
    return (
        db.query(ContractTermPreset)
        .filter(
            ContractTermPreset.company_id == company_id,
            ContractTermPreset.archived_at.is_(None),
        )
        .order_by(ContractTermPreset.name)
        .all()
    )


def get_preset(db: Session, company_id: int, preset_id: int) -> ContractTermPreset:
    preset = db.get(ContractTermPreset, preset_id)
    if preset is None or preset.company_id != company_id or preset.archived_at is not None:
        raise PresetNotFound(str(preset_id))
    return preset


def _save(db: Session, preset: ContractTermPreset) -> None:
    """Flush inside a savepoint, so a duplicate name leaves the transaction usable."""
    try:
        with db.begin_nested():
            db.add(preset)
            db.flush()
    except IntegrityError as exc:
        raise PresetNameTaken(preset.name) from exc


def create_preset(
    db: Session, company_id: int, account: UserAccount, name: str, terms: dict[str, object]
) -> ContractTermPreset:
    preset = ContractTermPreset(
        company_id=company_id,
        name=name.strip(),
        terms=clean_terms(db, terms),
        created_by_user_account_id=account.id,
    )
    _save(db, preset)
    return preset


def update_preset(
    db: Session, preset: ContractTermPreset, name: str, terms: dict[str, object]
) -> ContractTermPreset:
    preset.terms = clean_terms(db, terms)
    preset.name = name.strip()
    _save(db, preset)
    return preset


def archive_preset(db: Session, preset: ContractTermPreset) -> None:
    """Archived, not deleted — contracts drawn up from it still point at it."""
    preset.archived_at = utcnow()
    db.flush()
