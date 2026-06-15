"""
FastAPI dependency providers for authentication and authorization.

DEC-auth-split: Access tokens are short-lived JWTs (15 min) sent as Bearer tokens.
Identity is extracted from the verified JWT, never from the request body (T-03-06, dev-spec §10.5).

Dependencies provided:
- get_current_staff_user: decodes Bearer access token, loads StaffUser, rejects if inactive
- require_role(*roles): dependency factory enforcing role membership from the token's role claim
- require_admin: convenience shorthand for require_role(StaffRole.admin)
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token
from app.models.enums import StaffRole
from app.models.staff import StaffUser

# HTTP Bearer token extractor — auto_error=False so we can return 401 (not 403) on missing header
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_staff_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffUser:
    """Extract and verify the Bearer access token, load the staff user.

    Raises HTTP 401 if:
    - No Authorization header is present
    - The token is missing, malformed, expired, or has an invalid signature
    - The token type is not 'access' (rejects refresh tokens used as access tokens)
    - The staff_user no longer exists in the database

    Raises HTTP 403 if:
    - The staff_user account is inactive (is_active=False)

    Returns:
        The authenticated StaffUser ORM object.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type="access")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Extract the subject (staff_user id) from the verified token
    # T-03-06: identity comes ONLY from the verified token, never from the body
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        staff_user_id = int(subject)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: invalid subject format",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Load the user from DB to confirm they still exist and check is_active
    user: StaffUser | None = (
        db.query(StaffUser).filter(StaffUser.id == staff_user_id).first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user


def require_role(*roles: StaffRole) -> Callable[[StaffUser], StaffUser]:
    """Dependency factory that enforces role-based access control.

    Creates a FastAPI dependency that checks the current user's role against
    the allowed set. Authorization is enforced at the API layer, never the UI
    (REQ-roles, dev-spec §10.5, T-03-04).

    Args:
        *roles: The allowed StaffRole values for this endpoint.

    Returns:
        A dependency callable that returns the current user if authorized,
        or raises HTTP 403 if their role is not in the allowed set.

    Usage::

        @router.get("/admin/users")
        def list_users(current_user: StaffUser = Depends(require_role(StaffRole.admin))):
            ...
    """

    def _check_role(
        current_user: StaffUser = Depends(get_current_staff_user),
    ) -> StaffUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: requires one of {[r.value for r in roles]}",
            )
        return current_user

    return _check_role


# ── Convenience shortcuts ──────────────────────────────────────────────────────

#: Dependency that allows only admin users.
require_admin = require_role(StaffRole.admin)

#: Dependency that allows analyst and admin users.
require_analyst_or_admin = require_role(StaffRole.analyst, StaffRole.admin)
