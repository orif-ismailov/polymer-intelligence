"""
Audit log writer for privileged staff actions.

REQ-nfr-security: all privileged actions must write an audit_log row with:
  - staff_user_id: who performed the action (from the verified JWT sub, never from body)
  - action: e.g. 'auth.login', 'request.status_change', 'report.approve'
  - entity: the table/entity type affected (e.g. 'staff_users', 'requests')
  - entity_id: the affected row id (as text for schema flexibility)
  - details: optional JSONB context (e.g. IP address, old/new status values)

T-03-07: Repudiation — privileged actions are traced via this service.
T-03-06: Identity comes from the JWT sub claim, never from the request body.
         Callers pass staff_user_id extracted from the verified token.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.staff import AuditLog


def write_audit(
    db: Session,
    staff_user_id: int | None,
    action: str,
    entity: str,
    entity_id: str,
    details: dict[str, object] | None = None,
) -> AuditLog:
    """Insert an audit_log row for a privileged action.

    Args:
        db: The active SQLAlchemy session.
        staff_user_id: The id of the acting staff user (from verified JWT, never body).
                       May be None for system-initiated actions.
        action: The action being logged (e.g. 'auth.login', 'request.status_change').
        entity: The entity type being affected (e.g. 'staff_users', 'requests').
        entity_id: The id of the affected entity as a string.
        details: Optional JSONB context (e.g. {'ip': '127.0.0.1', 'old_status': 'new'}).

    Returns:
        The created AuditLog instance (added to the session, not yet committed).

    Note:
        This function calls db.flush() to get the generated id but does NOT commit.
        The caller is responsible for committing the transaction. This ensures that
        audit rows are committed together with the action they trace — preventing
        orphan audit rows if the action fails.
    """
    audit_row = AuditLog(
        staff_user_id=staff_user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(audit_row)
    db.flush()  # flush to DB without committing — caller commits the full transaction
    return audit_row
