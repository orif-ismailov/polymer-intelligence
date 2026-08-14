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
    role: str  # The staff_role value — useful for the dashboard UI routing
