"""
Substance registry service (P5 W2 — T2.2).

Reads and writes the local registry of regulated chemistry. There is no national
machine-readable source (INTEGRATIONS.md §4), so this table is the truth and the
admin panel is how it is corrected between seed revisions.

Two rules encoded here rather than in the router:

- **Search has to find a substance the way a seller names it.** "ПНД" is not a
  substring of "Полиэтилен", so synonyms are searched as first-class values, not
  as a JSON blob.
- **An operator edit takes the row out of the seed's hands** (`seed_revision`
  goes NULL). Otherwise the next deploy would silently undo a correction someone
  made in the panel.

Service axiom (DEC-dep-owns-commit): flush only — the router owns the commit.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.compliance import Substance
from app.models.enums import RegulationLevel
from app.schemas.substance import SubstanceIn
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)

#: Cap on picker results — the seller is typing, not browsing a catalog.
DEFAULT_SEARCH_LIMIT = 20


class SubstanceExists(Exception):
    """A substance with this code or CAS is already registered."""


def _matches(term: str) -> sa.ColumnElement[bool]:
    """Everything a person might type into the picker.

    Synonyms are expanded with `jsonb_array_elements_text` instead of casting the
    array to text: a substring match against the raw JSON would also match on
    punctuation and would rank a stray "[" as a hit.
    """
    pattern = f"%{term}%"
    synonym_hit = sa.text(
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(substances.synonyms) AS syn "
        "WHERE syn ILIKE :syn_pattern)"
    ).bindparams(syn_pattern=pattern)
    return sa.or_(
        Substance.code.ilike(pattern),
        Substance.name_ru.ilike(pattern),
        Substance.name_uz.ilike(pattern),
        Substance.name_en.ilike(pattern),
        Substance.cas.ilike(pattern),
        Substance.hs_code.ilike(pattern),
        synonym_hit,
    )


def search(db: Session, q: str, *, limit: int = DEFAULT_SEARCH_LIMIT) -> list[Substance]:
    """Active substances matching a free-text term (name / synonym / CAS / HS).

    An empty term returns nothing rather than the whole registry: the picker
    opens empty, and dumping every regulated chemical into it would suggest the
    seller is meant to pick one.
    """
    term = q.strip()
    if not term:
        return []
    return (
        db.query(Substance)
        .filter(Substance.is_active.is_(True), _matches(term))
        .order_by(Substance.name_ru)
        .limit(limit)
        .all()
    )


def list_all(
    db: Session,
    *,
    q: str | None = None,
    level: RegulationLevel | None = None,
    include_inactive: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[Substance]:
    """The admin list: every row, optionally filtered by term and level."""
    query = db.query(Substance)
    if not include_inactive:
        query = query.filter(Substance.is_active.is_(True))
    if level is not None:
        query = query.filter(Substance.regulation_level == level)
    if q and q.strip():
        query = query.filter(_matches(q.strip()))
    return query.order_by(Substance.name_ru).limit(limit).offset(offset).all()


def get(db: Session, substance_id: int) -> Substance | None:
    return db.get(Substance, substance_id)


def get_by_code(db: Session, code: str) -> Substance | None:
    return db.query(Substance).filter(Substance.code == code).first()


def resolve(
    db: Session,
    *,
    cas: str | None = None,
    hs_code: str | None = None,
    name: str | None = None,
) -> Substance | None:
    """Find the registry row an identifier or a name refers to.

    Tried in order of how much the input actually pins down: CAS is exact, an HS
    code narrows to a heading, a name is a guess. Used both by the AI suggestion
    (which returns all three) and by a seller typing a CAS by hand.
    """
    if cas and cas.strip():
        row = db.query(Substance).filter(Substance.cas == cas.strip()).first()
        if row is not None:
            return row
    if hs_code and hs_code.strip():
        row = db.query(Substance).filter(Substance.hs_code == hs_code.strip()).first()
        if row is not None:
            return row
    if name and name.strip():
        matches = search(db, name.strip(), limit=2)
        # Exactly one hit is a resolution; two is an ambiguity we must not guess.
        if len(matches) == 1:
            return matches[0]
    return None


def _assert_free(db: Session, data: SubstanceIn, *, exclude_id: int | None = None) -> None:
    """Reject a colliding code/CAS as a domain error, not an IntegrityError."""
    clash = db.query(Substance).filter(
        sa.or_(
            Substance.code == data.code,
            *([Substance.cas == data.cas] if data.cas else []),
        )
    )
    if exclude_id is not None:
        clash = clash.filter(Substance.id != exclude_id)
    if clash.first() is not None:
        raise SubstanceExists(data.code)


def _apply(row: Substance, data: SubstanceIn) -> None:
    row.code = data.code
    row.name_ru = data.name_ru
    row.name_uz = data.name_uz
    row.name_en = data.name_en
    row.hs_code = data.hs_code
    row.cas = data.cas
    row.hazard_class = data.hazard_class
    row.regulation_level = data.regulation_level
    row.regulation_regime = data.regulation_regime
    row.threshold_concentration_pct = data.threshold_concentration_pct
    row.exemption_annual_limit = data.exemption_annual_limit
    row.exemption_unit = data.exemption_unit
    row.license_category = data.license_category
    row.required_docs = list(data.required_docs)
    row.synonyms = list(data.synonyms)
    row.source_act = data.source_act
    row.is_active = data.is_active


def create(db: Session, data: SubstanceIn, *, staff_user_id: int) -> Substance:
    """Register a substance by hand. Does NOT commit."""
    _assert_free(db, data)
    row = Substance(code=data.code, name_ru=data.name_ru, hs_code=data.hs_code)
    _apply(row, data)
    #: Hand-made rows are never seed-owned, so a later revision leaves them be.
    row.seed_revision = None
    db.add(row)
    db.flush()
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="substance.create",
        entity="substances",
        entity_id=str(row.id),
        details={"code": row.code, "level": str(row.regulation_level)},
    )
    logger.info("substance.create", extra={"substance_id": row.id, "code": row.code})
    return row


def update(db: Session, row: Substance, data: SubstanceIn, *, staff_user_id: int) -> Substance:
    """Replace a registry row from the admin panel. Does NOT commit.

    Clears `seed_revision`: from here on the row belongs to the operator, and a
    future seed revision must not overwrite their correction.
    """
    _assert_free(db, data, exclude_id=row.id)
    before_level = str(row.regulation_level)
    _apply(row, data)
    row.seed_revision = None
    db.flush()
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="substance.update",
        entity="substances",
        entity_id=str(row.id),
        details={
            "code": row.code,
            "level_from": before_level,
            "level_to": str(row.regulation_level),
        },
    )
    logger.info("substance.update", extra={"substance_id": row.id, "code": row.code})
    return row


def set_active(db: Session, row: Substance, *, active: bool, staff_user_id: int) -> Substance:
    """Hide/restore a registry row. Does NOT commit.

    Deactivation rather than deletion: offers point at substances, and a blocked
    offer has to stay explainable after the list it was blocked by is superseded.
    """
    row.is_active = active
    db.flush()
    write_audit(
        db=db,
        staff_user_id=staff_user_id,
        action="substance.activate" if active else "substance.deactivate",
        entity="substances",
        entity_id=str(row.id),
        details={"code": row.code},
    )
    return row
