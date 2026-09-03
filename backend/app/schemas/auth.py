"""
Auth Pydantic schemas: request/response models for the auth API.

REQ-nfr-security: identity derives only from the verified JWT, never from the
request body. These schemas define the ONLY inputs accepted by the auth endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Request body for POST /auth/login.

    Only email and password accepted — no id or role field
    to prevent body-supplied identity injection (T-03-06, dev-spec §10.5).

    Note: email is typed as str (not EmailStr) to avoid requiring the optional
    email-validator package. The DB lookup is case-sensitive on the stored email;
    callers should normalize to lowercase before inserting (see seed_staff.py).
    """

    email: str
    password: str


class TokenResponse(BaseModel):
    """Response body for a successful login or refresh.

    Returns the short-lived access token only.
    The refresh token is delivered exclusively via httpOnly cookie (T-03-05).
    """

    access_token: str
    # noqa S105: "bearer" is the RFC 6750 scheme name, not a credential.
    token_type: str = "bearer"  # noqa: S105
    is_admin: bool  # Drives dashboard UI routing; the API re-checks it on every request


class MeResponse(BaseModel):
    """Response body for GET /auth/me — who the caller is and what they may reach.

    The access token carries no authorization claim, so this is how the dashboard
    learns whether to render admin-only chrome. It exists because the token lives
    in memory only: after a page reload the dashboard has re-minted a token from
    the refresh cookie and knows nothing else about the session.

    Answering from the staff row rather than the token is what makes revocation
    immediate — a deactivated account fails here on the next poll instead of
    staying privileged until its 15-minute token expires.
    """

    id: int
    email: str
    full_name: str
    is_admin: bool
    access: dict[str, str]
    """Every page this caller can reach, as `{page: 'read' | 'write'}`.

    An administrator gets the whole catalog at `write`, computed rather than
    stored, so their reach cannot fall behind a page added later. This is what
    the dashboard gates its navigation on — a courtesy, not the boundary: the
    API re-checks on every request."""
